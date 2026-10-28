"""실제 Firestore 저장소 코드(쿼리 · 정렬 · 필터)를 로컬 에뮬레이터로 확인한다.

    firebase emulators:start --only firestore --project demo-mission2   # 다른 터미널
    TEST_FIRESTORE_EMULATOR=127.0.0.1:8080 pytest tests/test_firestore_emulator.py

변수가 없으면 건너뛴다(기본 테스트는 네트워크 없이 돈다).
"""
import os

import pytest

HOST = os.getenv("TEST_FIRESTORE_EMULATOR")
pytestmark = pytest.mark.skipif(not HOST, reason="TEST_FIRESTORE_EMULATOR 미설정")


@pytest.fixture
def db(monkeypatch):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", HOST)
    client = firestore.Client(project="demo-test", credentials=AnonymousCredentials())
    for name in ("data", "conversations"):
        for doc in client.collection(name).stream():
            doc.reference.delete()
    return client


def test_data_repository_roundtrip(db):
    from app.errors import AppError
    from app.repositories import DataRepository
    from app.schemas import DataIn
    from app.services.data_service import DataService

    svc = DataService(DataRepository(db), cache_seconds=0)
    b = svc.create(DataIn(date="2026-01-11", value=2))
    a = svc.create(DataIn(date="2026-01-04", value=1, memo="m"))
    assert [p["date"] for p in svc.all_points()] == ["2026-01-04", "2026-01-11"]   # order_by("date")
    with pytest.raises(AppError) as e:
        svc.create(DataIn(date="2026-01-04", value=3))                            # where(date ==)
    assert e.value.status == 409
    assert svc.update(b["id"], DataIn(date="2026-01-18", value=5))["value"] == 5
    svc.delete(a["id"])
    assert [p["date"] for p in svc.all_points()] == ["2026-01-18"]


def test_conversation_repository_roundtrip(db):
    import time
    from app.repositories import ConversationRepository
    from app.schemas import Message
    from app.services.conversation_service import ConversationService

    svc = ConversationService(ConversationRepository(db))
    a = svc.create([Message(role="user", content="첫 대화 질문")])
    time.sleep(0.01)
    b = svc.create([Message(role="user", content="두 번째")], title="제목")
    time.sleep(0.01)
    svc.append(a["id"], [{"role": "assistant", "content": "답", "tool_calls": [{"name": "get_data_summary", "arguments": {}}]}])
    items = svc.list(10)["items"]
    assert [i["id"] for i in items] == [a["id"], b["id"]]            # updated_at 내림차순
    assert "messages" not in items[0] and items[0]["message_count"] == 2   # select() 로 messages 제외
    full = svc.get(a["id"])
    assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
    assert full["messages"][1]["tool_calls"][0]["name"] == "get_data_summary"
    svc.delete(b["id"])
    assert svc.list(10)["count"] == 1
