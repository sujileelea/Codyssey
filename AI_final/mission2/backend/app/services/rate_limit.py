"""채팅 호출 제한(과금 보호) — 접속 주소별 분당 횟수 + 서버 전체 하루 횟수.

무료 서버 1대에서 도는 메모리 카운터라 재시작하면 초기화된다. 공개 URL 에 키가 붙어 있으므로
'누군가 반복 호출해 요금이 쌓이는 것' 을 막는 최소 장치다.
"""
import threading
import time
from collections import defaultdict, deque
from datetime import date

from ..errors import AppError


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int):
        self.per_minute, self.per_day = per_minute, per_day
        self._hits: dict[str, deque] = defaultdict(deque)
        self._day, self._day_count = date.today(), 0
        self._lock = threading.Lock()

    def check(self, client: str) -> None:
        now = time.monotonic()
        with self._lock:
            if self._day != date.today():
                self._day, self._day_count = date.today(), 0
            if self._day_count >= self.per_day:
                raise AppError(429, "DAILY_LIMIT", "오늘 AI 대화 한도에 도달했습니다. 내일 다시 이용해 주세요.")
            hits = self._hits[client]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                wait = int(60 - (now - hits[0])) + 1
                raise AppError(429, "RATE_LIMITED", f"질문이 너무 잦습니다. {wait}초 뒤 다시 시도해 주세요.")
            hits.append(now)
            self._day_count += 1
