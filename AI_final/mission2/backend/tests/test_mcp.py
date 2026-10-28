"""MCP 서버(보너스) — 인프로세스 클라이언트로 도구 목록 · 호출 경로 · 오류 전달을 확인한다(HTTP 는 가짜)."""
import asyncio
import json

import mcp_server
from app.services.tools import TOOLS
from mcp.client import Client


def run(coro):
    return asyncio.run(coro)


def test_tools_match_web_function_calling(monkeypatch):
    async def go():
        async with Client(mcp_server.server) as c:
            return await c.list_tools()
    tools = {t.name: t for t in run(go()).tools}
    assert set(tools) == set(TOOLS) | {"ask_assistant"}
    for name, (desc, _) in TOOLS.items():
        assert tools[name].description == desc                       # 웹 GPT 도구와 같은 설명


def test_tool_calls_hit_rest_api(monkeypatch):
    seen = []

    async def fake_call(method, path, **kwargs):
        seen.append((method, path, kwargs))
        if path == "/api/data/statistics":
            return {"moving_average": {"window": 4, "series": [{"date": str(i), "value": i, "ma": i} for i in range(20)]}}
        if path == "/api/conversations/missing":
            return {"error": "해당 대화를 찾을 수 없습니다."}
        return {"ok": True}
    monkeypatch.setattr(mcp_server, "_call", fake_call)

    async def go():
        async with Client(mcp_server.server) as c:
            out = {}
            for name, args in [("query_data", {"start": "2025-11-01", "limit": 500}), ("get_statistics", {}),
                               ("ask_assistant", {"question": "추세는?"}), ("get_conversation", {"conversation_id": "missing"})]:
                res = await c.call_tool(name, args)
                out[name] = res.structured_content or json.loads(res.content[0].text)
            return out
    out = run(go())
    assert seen[0] == ("GET", "/api/data", {"params": {"order": "asc", "limit": 120, "start": "2025-11-01"}})   # 상한 120
    assert len(out["get_statistics"]["moving_average_recent"]["series"]) == 13
    assert seen[2] == ("POST", "/api/chat", {"json": {"message": "추세는?"}})
    assert out["get_conversation"] == {"error": "해당 대화를 찾을 수 없습니다."}
