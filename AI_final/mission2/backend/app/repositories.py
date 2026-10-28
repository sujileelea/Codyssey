"""Firestore 읽기/쓰기 — 컬렉션 구조를 아는 유일한 층.

컬렉션
- data/{자동 ID}           {date: "YYYY-MM-DD", value: number, memo: string, created_at, updated_at}
- conversations/{자동 ID}  {title, messages: [{role, content, created_at, tool_calls?}], message_count, created_at, updated_at}

date 를 문자열(ISO)로 저장해 사전순 = 시간순으로 정렬 · 범위 조회가 된다.
"""
from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter


def now() -> datetime:
    return datetime.now(timezone.utc)


def _with_id(snap) -> dict:
    return {"id": snap.id, **snap.to_dict()}


class DataRepository:
    def __init__(self, db):
        self.col = db.collection("data")

    def list_all(self) -> list[dict]:
        return [_with_id(s) for s in self.col.order_by("date").stream()]

    def get(self, item_id: str) -> dict | None:
        snap = self.col.document(item_id).get()
        return _with_id(snap) if snap.exists else None

    def find_by_date(self, day: str) -> list[dict]:
        return [_with_id(s) for s in self.col.where(filter=FieldFilter("date", "==", day)).limit(2).stream()]

    def create(self, fields: dict) -> dict:
        ref = self.col.document()
        doc = {**fields, "created_at": now(), "updated_at": now()}
        ref.set(doc)
        return {"id": ref.id, **doc}

    def update(self, item_id: str, fields: dict) -> dict:
        ref = self.col.document(item_id)
        ref.update({**fields, "updated_at": now()})
        return _with_id(ref.get())

    def delete(self, item_id: str) -> None:
        self.col.document(item_id).delete()


class ConversationRepository:
    LIST_FIELDS = ["title", "message_count", "preview", "created_at", "updated_at"]

    def __init__(self, db):
        self.col = db.collection("conversations")

    def list(self, limit: int) -> list[dict]:
        # 목록에는 messages 를 싣지 않는다(필드 선택) — 응답이 가볍고 대화가 길어져도 목록 속도가 같다
        query = self.col.select(self.LIST_FIELDS).order_by("updated_at", direction="DESCENDING").limit(limit)
        return [_with_id(s) for s in query.stream()]

    def get(self, conv_id: str) -> dict | None:
        snap = self.col.document(conv_id).get()
        return _with_id(snap) if snap.exists else None

    def create(self, fields: dict) -> dict:
        ref = self.col.document()
        doc = {**fields, "created_at": now(), "updated_at": now()}
        ref.set(doc)
        return {"id": ref.id, **doc}

    def update(self, conv_id: str, fields: dict) -> dict:
        ref = self.col.document(conv_id)
        ref.update({**fields, "updated_at": now()})
        return _with_id(ref.get())

    def delete(self, conv_id: str) -> None:
        self.col.document(conv_id).delete()
