"""테스트 공통 — Firestore · OpenAI 대신 메모리 저장소와 가짜 GPT 를 끼운다(네트워크 · 키 불필요)."""
import itertools
import os

# 실제 키 · DB 에 닿지 않도록 .env 를 끄고 설정을 비운다(app 을 import 하기 전)
os.environ["APP_ENV"] = "test"
for name in ("OPENAI_API_KEY", "FIREBASE_SERVICE_ACCOUNT_JSON", "FIREBASE_SERVICE_ACCOUNT_PATH", "FIRESTORE_EMULATOR_HOST"):
    os.environ[name] = ""

import pytest
from fastapi.testclient import TestClient

import main
from app import deps
from app.repositories import now
from app.services.conversation_service import ConversationService
from app.services.data_service import DataService

_ids = itertools.count(1)


class MemoryDataRepository:
    """DataRepository 와 같은 메서드를 가진 메모리 구현."""

    def __init__(self, rows=()):
        self.docs = {}
        for r in rows:
            self.create(r)

    def list_all(self):
        return sorted(({"id": k, **v} for k, v in self.docs.items()), key=lambda r: r["date"])

    def get(self, item_id):
        return {"id": item_id, **self.docs[item_id]} if item_id in self.docs else None

    def find_by_date(self, day):
        return [{"id": k, **v} for k, v in self.docs.items() if v["date"] == day][:2]

    def create(self, fields):
        item_id = f"d{next(_ids):05d}"
        self.docs[item_id] = {**fields, "created_at": now(), "updated_at": now()}
        return {"id": item_id, **self.docs[item_id]}

    def update(self, item_id, fields):
        self.docs[item_id].update(fields, updated_at=now())
        return self.get(item_id)

    def delete(self, item_id):
        self.docs.pop(item_id, None)


class MemoryConversationRepository:
    def __init__(self):
        self.docs = {}

    def list(self, limit):
        rows = sorted(({"id": k, **v} for k, v in self.docs.items()), key=lambda r: r["updated_at"], reverse=True)
        return [{k: r[k] for k in ("id", "title", "message_count", "preview", "created_at", "updated_at")} for r in rows[:limit]]

    def get(self, conv_id):
        return {"id": conv_id, **self.docs[conv_id]} if conv_id in self.docs else None

    def create(self, fields):
        conv_id = f"c{next(_ids):05d}"
        self.docs[conv_id] = {**fields, "created_at": now(), "updated_at": now()}
        return self.get(conv_id)

    def update(self, conv_id, fields):
        self.docs[conv_id].update(fields, updated_at=now())
        return self.get(conv_id)

    def delete(self, conv_id):
        self.docs.pop(conv_id, None)


def weekly(values, start="2025-01-05", memo=None):
    """일요일부터 1주 간격의 행 목록."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return [{"date": (d0 + timedelta(weeks=i)).isoformat(), "value": v, "memo": (memo or {}).get(i, "")}
            for i, v in enumerate(values)]


@pytest.fixture
def data_repo():
    return MemoryDataRepository()


@pytest.fixture
def conv_repo():
    return MemoryConversationRepository()


@pytest.fixture
def client(data_repo, conv_repo):
    svc = DataService(data_repo, cache_seconds=0)
    conv = ConversationService(conv_repo)
    main.app.dependency_overrides[deps.get_data_service] = lambda: svc
    main.app.dependency_overrides[deps.get_conversation_service] = lambda: conv
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
