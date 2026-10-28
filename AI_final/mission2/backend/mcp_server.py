"""MCP 서버(보너스) — 웹 채팅의 GPT 도구와 같은 기능을 MCP 클라이언트(Claude Desktop · Claude Code · MCP Inspector 등)에 연다.

도구 이름 · 설명은 app/services/tools.py 의 TOOLS 를 그대로 쓰고, 실행은 배포된(또는 로컬) REST API 를 HTTP 로 부른다.
즉 '같은 내부 기능' 을 웹(Function Calling)과 외부 클라이언트(MCP) 두 채널이 함께 쓴다.

    API_BASE_URL=https://<백엔드>.onrender.com python mcp_server.py      # stdio 로 실행(클라이언트가 띄움)
    python scripts/check_mcp.py                                           # 호출 흐름 검증
"""
import logging
import os

import httpx
from mcp.server.mcpserver import MCPServer

from app.services.tools import TOOLS

API = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = httpx.Timeout(90.0, connect=30.0)       # 무료 서버 콜드스타트(최대 1분) 대기
logging.getLogger("httpx").setLevel(logging.WARNING)

server = MCPServer(
    name="my-data-assistant",
    title="내 데이터 AI 비서",
    instructions="사용자가 저장한 시계열 데이터(미국 'AI shopping' 검색 관심도, 주간)를 조회 · 분석한다. "
                 "전체 개요는 get_data_summary, 특정 기간 값은 query_data, 연도 비교 · 변화 폭은 get_statistics, "
                 "지난 대화는 list_conversations → get_conversation, 서버 쪽 AI 비서에게 바로 묻기는 ask_assistant.",
    version="1.0.0",
)


async def _call(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=API, timeout=TIMEOUT) as client:
        res = await client.request(method, path, **kwargs)
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    if res.is_error:
        detail = body.get("detail") if isinstance(body, dict) else None
        return {"error": (detail or {}).get("message", f"HTTP {res.status_code}") if isinstance(detail, dict) else str(detail)}
    return body


def _desc(name: str) -> str:
    return TOOLS[name][0]


@server.tool(description=_desc("get_data_summary"))
async def get_data_summary() -> dict:
    return await _call("GET", "/api/data/summary")


@server.tool(description=_desc("query_data"))
async def query_data(start: str | None = None, end: str | None = None, order: str = "asc", limit: int = 60) -> dict:
    params = {"order": order, "limit": max(1, min(limit, 120))}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    return await _call("GET", "/api/data", params=params)


@server.tool(description=_desc("get_statistics"))
async def get_statistics(ma_window: int = 4) -> dict:
    st = await _call("GET", "/api/data/statistics", params={"ma_window": ma_window})
    if "moving_average" in st:
        series = st.pop("moving_average")
        st["moving_average_recent"] = {"window": series["window"], "series": series["series"][-13:]}
    return st


@server.tool(description=_desc("list_conversations"))
async def list_conversations(limit: int = 10) -> dict:
    return await _call("GET", "/api/conversations", params={"limit": max(1, min(limit, 30))})


@server.tool(description=_desc("get_conversation"))
async def get_conversation(conversation_id: str) -> dict:
    return await _call("GET", f"/api/conversations/{conversation_id}")


@server.tool(description="내 데이터 AI 비서에게 질문한다. 서버가 데이터 요약을 시스템 프롬프트에 주입하고 GPT(필요하면 도구 포함)로 답한 뒤 "
                         "대화를 저장한다. 답 · 호출한 도구 · 대화 ID 를 돌려준다.")
async def ask_assistant(question: str, conversation_id: str | None = None) -> dict:
    payload = {"message": question}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return await _call("POST", "/api/chat", json=payload)


if __name__ == "__main__":
    server.run()      # stdio
