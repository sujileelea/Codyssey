"""데이터 CRUD 규칙.

- 같은 날짜는 하나만(시계열에서 한 시점 = 한 값) — 겹치면 409
- 전체 목록은 60초 캐시한다. 요약 · 통계 · 채팅이 매번 전체를 읽으므로 Firestore 읽기 횟수(무료 한도)를 아낀다.
  이 서버를 거친 쓰기는 즉시 캐시를 비우고, 콘솔에서 직접 고친 값은 최대 60초 뒤 반영된다.
"""
import threading
import time
from datetime import date

from ..errors import AppError
from ..schemas import DataIn
from . import analysis

CACHE_SECONDS = 60


class DataService:
    def __init__(self, repo, cache_seconds: float = CACHE_SECONDS):
        self.repo = repo
        self.cache_seconds = cache_seconds
        self._cache: list[dict] | None = None
        self._cached_at = 0.0
        self._lock = threading.Lock()

    # ── 읽기 ──
    def all_points(self) -> list[dict]:
        """날짜 오름차순 전체(캐시)."""
        with self._lock:
            if self._cache is None or time.monotonic() - self._cached_at > self.cache_seconds:
                self._cache = sorted(self.repo.list_all(), key=lambda r: r["date"])
                self._cached_at = time.monotonic()
            return list(self._cache)

    def list(self, start: date | None = None, end: date | None = None,
             order: str = "asc", limit: int = 1000) -> dict:
        points = self.all_points()
        rows = [p for p in points
                if (start is None or p["date"] >= start.isoformat()) and (end is None or p["date"] <= end.isoformat())]
        if order == "desc":
            rows.reverse()
        rows = rows[:limit]
        return {"count": len(rows), "total": len(points), "items": rows}

    def summary(self) -> dict:
        return analysis.summarize(self.all_points())

    def statistics(self, ma_window: int = 4) -> dict:
        return analysis.statistics(self.all_points(), ma_window)

    # ── 쓰기 ──
    def create(self, body: DataIn) -> dict:
        day = body.date.isoformat()
        if self.repo.find_by_date(day):
            raise AppError(409, "DUPLICATE_DATE", f"{day} 데이터가 이미 있습니다. 목록에서 수정해 주세요.")
        row = self.repo.create({"date": day, "value": body.value, "memo": body.memo})
        self.invalidate()
        return row

    def update(self, item_id: str, body: DataIn) -> dict:
        self._require(item_id)
        day = body.date.isoformat()
        if any(r["id"] != item_id for r in self.repo.find_by_date(day)):
            raise AppError(409, "DUPLICATE_DATE", f"{day} 데이터가 이미 있습니다. 다른 날짜를 고르거나 그 행을 수정해 주세요.")
        row = self.repo.update(item_id, {"date": day, "value": body.value, "memo": body.memo})
        self.invalidate()
        return row

    def delete(self, item_id: str) -> dict:
        self._require(item_id)
        self.repo.delete(item_id)
        self.invalidate()
        return {"id": item_id, "deleted": True}

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None

    def _require(self, item_id: str) -> dict:
        row = self.repo.get(item_id)
        if row is None:
            raise AppError(404, "NOT_FOUND", "해당 데이터를 찾을 수 없습니다. 이미 삭제됐을 수 있습니다.")
        return row
