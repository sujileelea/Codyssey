"""Function Calling(보너스) — 도구 스키마 · 실행 · 채팅 왕복 · 기록."""
import json
from types import SimpleNamespace

from app.services.llm import LLMResult
from app.services.tools import TOOL_SPECS, ToolRunner
from conftest import weekly


def call(name, args, cid="call_1"):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def tool_turn(*calls):
    msg = {"role": "assistant", "tool_calls": [{"id": c.id, "type": "function",
                                                "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                               for c in calls]}
    return LLMResult(content="", finish_reason="tool_calls", tool_calls=list(calls), message=msg,
                     usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})


def test_specs_are_openai_function_schema():
    names = [t["function"]["name"] for t in TOOL_SPECS]
    assert names == ["get_data_summary", "query_data", "get_statistics", "list_conversations", "get_conversation"]
    q = TOOL_SPECS[1]["function"]["parameters"]
    assert q["type"] == "object" and set(q["properties"]) == {"start", "end", "order", "limit"}
    assert TOOL_SPECS[4]["function"]["parameters"]["required"] == ["conversation_id"]


def test_runner(client, data_repo, conv_repo):
    # client 픽스처가 서비스 조립을 끝낸 뒤의 저장소를 쓴다
    from app.services.conversation_service import ConversationService
    from app.services.data_service import DataService
    for r in weekly([1, 2, 3, 4, 5, 6], start="2026-01-04"):
        data_repo.create(r)
    run = ToolRunner(DataService(data_repo, 0), ConversationService(conv_repo)).run
    rows = run("query_data", '{"start": "2026-01-10", "end": "2026-01-25"}')["items"]
    assert [r["date"] for r in rows] == ["2026-01-11", "2026-01-18", "2026-01-25"]
    assert run("get_data_summary", "{}")["count"] == 6
    st = run("get_statistics", {"ma_window": 2})
    assert "moving_average" not in st and len(st["moving_average_recent"]["series"]) == 6
    assert "error" in run("query_data", '{"start": "어제"}')          # 인자 오류는 예외 대신 error
    assert "error" in run("get_conversation", '{"conversation_id": "none"}')
    assert "error" in run("delete_everything", "{}")


def test_chat_with_tool_round_trip(client, llm, data_repo, conv_repo):
    for r in weekly([10, 20, 30, 40, 50, 60, 70, 80], start="2025-11-02", memo={3: "블랙프라이데이 주"}):
        data_repo.create(r)
    llm.replies = [
        tool_turn(call("query_data", {"start": "2025-11-01", "end": "2025-11-30"})),
        LLMResult(content="2025년 11월은 10~40 범위였습니다.", finish_reason="stop",
                  usage={"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220}),
    ]
    body = client.post("/api/chat", json={"message": "2025년 11월 값 알려줘"}).json()
    assert body["reply"].startswith("2025년 11월")
    assert body["tool_calls"] == [{"name": "query_data", "arguments": {"start": "2025-11-01", "end": "2025-11-30"}}]
    assert body["usage"]["total_tokens"] == 330                                   # 두 번 호출한 토큰 합

    first, second = llm.calls
    assert first["tools"] and "도구를 호출해" in first["messages"][0]["content"]
    tool_msg = second["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"
    assert [r["date"] for r in json.loads(tool_msg["content"])["items"]][:2] == ["2025-11-02", "2025-11-09"]

    saved = conv_repo.get(body["conversation_id"])["messages"][-1]
    assert saved["tool_calls"][0]["name"] == "query_data"                         # 어떤 도구를 썼는지 함께 저장


def test_tool_rounds_are_capped(client, llm, data_repo):
    data_repo.create({"date": "2026-01-04", "value": 1, "memo": ""})
    llm.replies = [tool_turn(call("get_data_summary", {}, f"c{i}")) for i in range(3)] + \
                  [LLMResult(content="끝", finish_reason="stop")]
    body = client.post("/api/chat", json={"message": "q", "save": False}).json()
    assert body["reply"] == "끝" and len(body["tool_calls"]) == 3
    assert llm.calls[-1]["tools"] is None                                          # 마지막 차례는 도구 없이 답


def test_tools_off(client, llm, data_repo):
    data_repo.create({"date": "2026-01-04", "value": 1, "memo": ""})
    client.post("/api/chat", json={"message": "q", "use_tools": False, "save": False})
    assert llm.calls[0]["tools"] is None and "도구를 호출해" not in llm.calls[0]["messages"][0]["content"]
    assert client.get("/api/chat/tools").json()[0]["function"]["name"] == "get_data_summary"
