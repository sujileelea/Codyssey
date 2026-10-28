"""MCP 호출 흐름 검증 — MCP 클라이언트가 mcp_server.py 를 stdio 로 띄워 도구 목록을 받고 도구를 차례로 부른다.

    API_BASE_URL=http://localhost:8000 python scripts/check_mcp.py           # 로컬 서버
    API_BASE_URL=https://<백엔드>.onrender.com python scripts/check_mcp.py --ask "최근 추세는?"
    ... --log docs/mcp-check.log                                              # 결과를 파일로도 남김

흐름: 클라이언트 → (stdio, JSON-RPC) → MCP 서버 → (HTTPS) → FastAPI → Firestore / GPT
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

BACKEND = Path(__file__).resolve().parent.parent


def text_of(result) -> str:
    if getattr(result, "structured_content", None) is not None:
        return json.dumps(result.structured_content, ensure_ascii=False)
    return " ".join(getattr(c, "text", "") for c in result.content)


async def main(ask: str | None, log_path: Path | None) -> int:
    api = os.getenv("API_BASE_URL", "http://localhost:8000")
    lines: list[str] = []

    def out(s: str = "") -> None:
        print(s)
        lines.append(s)

    params = StdioServerParameters(command=sys.executable, args=[str(BACKEND / "mcp_server.py")],
                                   env={"API_BASE_URL": api}, cwd=str(BACKEND))
    out(f"# MCP 호출 검증 {datetime.now():%Y-%m-%d %H:%M} · API_BASE_URL={api}")
    async with Client(params) as client:
        tools = await client.list_tools()
        out(f"\n[1] tools/list → {len(tools.tools)}개: " + ", ".join(t.name for t in tools.tools))

        calls = [
            ("get_data_summary", {}),
            ("query_data", {"start": "2025-11-01", "end": "2025-11-30"}),
            ("get_statistics", {"ma_window": 4}),
            ("list_conversations", {"limit": 3}),
        ]
        if ask:
            calls.append(("ask_assistant", {"question": ask}))
        failed = 0
        for i, (name, args) in enumerate(calls, start=2):
            res = await client.call_tool(name, args)
            body = text_of(res)
            ok = not res.is_error and '"error"' not in body[:20]
            failed += not ok
            out(f"\n[{i}] tools/call {name} {json.dumps(args, ensure_ascii=False)} → {'성공' if ok else '실패'}")
            data = json.loads(body) if body.startswith("{") else {}
            if name == "get_data_summary" and ok:
                out(f"    기간 {data['period']} · {data['count']}개 · 평균 {data['metrics']['average']} · 추세 {data['trend']}")
            elif name == "query_data" and ok:
                out("    " + ", ".join(f"{r['date']}={r['value']:g}" + (f"({r['memo']})" if r["memo"] else "") for r in data["items"]))
            elif name == "get_statistics" and ok:
                out(f"    전년 동기 대비 {data['yoy']['change_pct']}% · 최대 상승 {data['largest_rise']['date']} {data['largest_rise']['change_pct']}%"
                    f" · 최고점 대비 {data['from_peak_pct']}%")
            elif name == "list_conversations" and ok:
                out(f"    {data['count']}건: " + " | ".join(c["title"] for c in data["items"]))
            elif name == "ask_assistant" and ok:
                out(f"    도구 {[t['name'] for t in data['tool_calls']]} · 대화 {data['conversation_id']}\n    답: {data['reply']}")
            else:
                out("    " + body[:300])
    out(f"\n결과: {len(calls) - failed}/{len(calls)} 성공")
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", help="ask_assistant 로 보낼 질문(GPT 호출 1회)")
    ap.add_argument("--log", type=Path, help="결과를 저장할 파일")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.ask, a.log)))
