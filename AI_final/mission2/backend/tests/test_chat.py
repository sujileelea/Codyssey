"""AI 대화 — 요약 주입 · 이전 대화 포함 · 자동 저장 · 호출 제한 · 오류 변환."""
from datetime import date

import openai
import httpx
import pytest

from app.config import get_settings
from app.errors import AppError
from app.services import analysis
from app.services.chat_service import build_system_prompt, fmt
from app.services.llm import LLMClient, LLMResult
from app.services.rate_limit import RateLimiter
from conftest import weekly


@pytest.fixture
def seeded(data_repo):
    for r in weekly([10, 20, 30, 40, 50, 60, 70, 100], start="2026-04-05", memo={7: "최고점"}):
        data_repo.create(r)


def test_fmt():
    assert (fmt(32000000.0), fmt(5.5), fmt(16.1449), fmt(None)) == ("32,000,000", "5.5", "16.14", "-")


def test_system_prompt_contains_summary():
    s = analysis.summarize(weekly([1, 2, 3, 4, 5, 6, 7, 8], start="2026-01-04", memo={3: "사건 A"}))
    prompt = build_system_prompt(s, get_settings(), today=date(2026, 3, 1))
    for text in ("[사용자 데이터 요약]", "데이터 기간: 2026-01-04 ~ 2026-02-22", "총 레코드: 8개", "최댓값 8(2026-02-22)",
                 "최근 트렌드(단기): 상승", "2026-01-25 = 4 (사건 A)", "오늘 날짜: 2026-03-01", get_settings().dataset_name):
        assert text in prompt, text
    empty = build_system_prompt(analysis.summarize([]), get_settings())
    assert "저장된 데이터가 없습니다" in empty


def test_chat_injects_summary_and_autosaves(client, llm, seeded, conv_repo):
    r = client.post("/api/chat", json={"message": "가장 높았던 때는?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "가짜 답변" and body["saved"] is True and body["model"] == "fake-gpt"
    assert body["context"]["count"] == 8 and body["usage"]["total_tokens"] == 15

    sent = llm.calls[0]["messages"]
    assert sent[0]["role"] == "system" and "최댓값 100(2026-05-24)" in sent[0]["content"]   # 요약이 주입됨
    assert sent[-1] == {"role": "user", "content": "가장 높았던 때는?"}

    conv_id = body["conversation_id"]
    assert conv_repo.get(conv_id)["message_count"] == 2                                      # 질문 + 답 자동 저장

    # 같은 대화로 이어서 묻기 → 이전 메시지가 함께 가고, 같은 문서에 이어 저장
    r = client.post("/api/chat", json={"message": "그 다음 주는?", "conversation_id": conv_id})
    assert r.json()["conversation_id"] == conv_id
    assert [m["role"] for m in llm.calls[1]["messages"]] == ["system", "user", "assistant", "user"]
    assert conv_repo.get(conv_id)["message_count"] == 4


def test_chat_reflects_data_change(client, llm, seeded):
    client.post("/api/chat", json={"message": "a", "save": False})
    client.post("/api/data", json={"date": "2026-06-07", "value": 300, "memo": "새 최고"})
    client.post("/api/chat", json={"message": "b", "save": False})
    assert "최댓값 300(2026-06-07)" in llm.calls[1]["messages"][0]["content"]               # 바뀐 데이터가 다음 질문에 반영


def test_chat_without_save_uses_history(client, llm, seeded, conv_repo):
    history = [{"role": "user", "content": "이전 질문"}, {"role": "assistant", "content": "이전 답"}]
    body = client.post("/api/chat", json={"message": "다음", "history": history, "save": False}).json()
    assert body["saved"] is False and body["conversation_id"] is None and not conv_repo.docs
    assert [m["content"] for m in llm.calls[0]["messages"][1:]] == ["이전 질문", "이전 답", "다음"]


def test_chat_validation_and_missing_conversation(client):
    assert client.post("/api/chat", json={"message": "  "}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 2001}).status_code == 422
    r = client.post("/api/chat", json={"message": "hi", "conversation_id": "missing"})
    assert r.status_code == 404


def test_empty_reply_fallback(client, llm, seeded):
    llm.replies = [LLMResult(content="", finish_reason="length")]
    assert "끊겼습니다" in client.post("/api/chat", json={"message": "q", "save": False}).json()["reply"]


def test_llm_error_is_reported(client, llm, seeded):
    llm.replies = [AppError(504, "AI_TIMEOUT", "AI 응답이 늦어 중단했습니다.")]
    r = client.post("/api/chat", json={"message": "q"})
    assert r.status_code == 504 and r.json()["detail"]["code"] == "AI_TIMEOUT"


def test_rate_limit(client, limiter, seeded):
    limiter.per_minute = 2
    codes = [client.post("/api/chat", json={"message": "q", "save": False}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    other = client.post("/api/chat", json={"message": "q", "save": False}, headers={"X-Forwarded-For": "10.0.0.9"})
    assert other.status_code == 200                                                          # 주소별로 센다
    daily = RateLimiter(per_minute=10, per_day=1)
    daily.check("a")
    with pytest.raises(AppError) as e:
        daily.check("b")
    assert e.value.code == "DAILY_LIMIT"


def test_prompt_preview(client, seeded, llm):
    body = client.get("/api/chat/prompt").json()
    assert body["summary"]["count"] == 8 and "[사용자 데이터 요약]" in body["system_prompt"]
    assert not llm.calls                                                                     # GPT 호출 없음


def test_llm_client_maps_openai_errors(monkeypatch):
    from dataclasses import replace
    settings = replace(get_settings(), openai_api_key="test-key")
    client = LLMClient(settings)
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

    def raise_(exc):
        def _create(**kwargs):
            raise exc
        return _create

    cases = [
        (openai.APITimeoutError(request=req), 504, "AI_TIMEOUT"),
        (openai.RateLimitError("rate", response=httpx.Response(429, request=req), body=None), 429, "AI_RATE_LIMITED"),
        (openai.RateLimitError("insufficient_quota", response=httpx.Response(429, request=req), body=None), 429, "AI_QUOTA"),
        (openai.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None), 503, "AI_AUTH"),
        (openai.APIConnectionError(request=req), 502, "AI_UNREACHABLE"),
        (openai.InternalServerError("boom", response=httpx.Response(500, request=req), body=None), 502, "AI_ERROR"),
    ]
    for exc, status, code in cases:
        monkeypatch.setattr(client.client.chat.completions, "create", raise_(exc))
        with pytest.raises(AppError) as e:
            client.complete([{"role": "user", "content": "q"}])
        assert (e.value.status, e.value.code) == (status, code)

    with pytest.raises(AppError) as e:
        LLMClient(get_settings())                                                            # 키 없음
    assert e.value.code == "AI_NOT_CONFIGURED"
