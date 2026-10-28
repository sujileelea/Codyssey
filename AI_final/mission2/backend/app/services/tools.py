"""GPT 도구(Function Calling, 보너스).

시스템 프롬프트의 요약은 '전체 개요' 라서 특정 달의 주별 값 · 연도별 비교 · 지난 대화 내용은 담지 못한다.
그런 질문이면 GPT 가 아래 도구를 골라 호출하고(이름 + JSON 인자), 서버가 내부 서비스로 실행해 결과를 돌려준 뒤
GPT 가 그 결과를 근거로 최종 답을 쓴다. 같은 도구 이름 · 설명을 MCP 서버(mcp_server.py)도 그대로 쓴다.
"""
import json
from datetime import date

from pydantic import BaseModel, Field, ValidationError

from ..errors import AppError

MAX_ROWS = 120


class QueryDataArgs(BaseModel):
    start: date | None = Field(None, description="시작 날짜(YYYY-MM-DD, 포함)")
    end: date | None = Field(None, description="끝 날짜(YYYY-MM-DD, 포함)")
    order: str = Field("asc", pattern="^(asc|desc)$", description="asc = 오래된 순, desc = 최신 순")
    limit: int = Field(60, ge=1, le=MAX_ROWS, description="최대 행 수")


class StatisticsArgs(BaseModel):
    ma_window: int = Field(4, ge=2, le=52, description="이동평균 창 크기")


class ListConversationsArgs(BaseModel):
    limit: int = Field(10, ge=1, le=30)


class GetConversationArgs(BaseModel):
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


def _function(name: str, description: str, model: type[BaseModel] | None) -> dict:
    params = {"type": "object", "properties": {}, "additionalProperties": False}
    if model:
        schema = model.model_json_schema()
        params["properties"] = {k: {kk: vv for kk, vv in v.items() if kk != "title"} for k, v in schema["properties"].items()}
        if schema.get("required"):
            params["required"] = schema["required"]
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


TOOLS = {
    "get_data_summary": (
        "저장된 시계열 데이터의 최신 요약(기간 · 개수 · 평균/최대/최소 · 단기/장기 추세 · 최근 값 · 월평균 · 메모 시점)을 다시 조회한다. "
        "대화 중 데이터가 바뀌었을 수 있을 때 쓴다.", None),
    "query_data": (
        "기간을 지정해 원자료(date, value, memo) 행을 조회한다. 요약에 없는 특정 달 · 주 · 사건 전후의 값을 확인할 때 쓴다.",
        QueryDataArgs),
    "get_statistics": (
        "추가 통계 — 연도별 평균과 전년 대비, 전년 같은 시기 대비, 직전 대비 최대 상승/하락, 변동성, 연속 방향, 최고점 대비, "
        "전체 월평균, 최근 이동평균을 조회한다. 연도 비교 · 변화 폭 질문에 쓴다.", StatisticsArgs),
    "list_conversations": ("저장된 지난 대화 목록(제목 · 미리보기 · 시각)을 최근 순으로 조회한다. '지난번에 물어본 것' 같은 질문에 쓴다.",
                           ListConversationsArgs),
    "get_conversation": ("지난 대화 하나의 메시지 전체를 조회한다. list_conversations 로 찾은 ID 를 넣는다.", GetConversationArgs),
}

TOOL_SPECS = [_function(name, desc, model) for name, (desc, model) in TOOLS.items()]


class ToolRunner:
    def __init__(self, data, conversations):
        self.data, self.conversations = data, conversations

    def run(self, name: str, raw_args: str | dict) -> dict:
        """도구 실행. 잘못된 이름 · 인자 · 없는 ID 는 예외 대신 {"error"} 로 돌려 GPT 가 고쳐 부르게 한다."""
        if name not in TOOLS:
            return {"error": f"알 수 없는 도구: {name}"}
        try:
            args = json.loads(raw_args or "{}") if isinstance(raw_args, str) else dict(raw_args or {})
            model = TOOLS[name][1]
            parsed = model(**args) if model else None
            return getattr(self, name)(parsed)
        except (ValueError, ValidationError) as e:
            return {"error": f"인자 오류: {e}"}
        except AppError as e:
            return {"error": e.message}

    def get_data_summary(self, _):
        return self.data.summary()

    def query_data(self, a: QueryDataArgs):
        return self.data.list(a.start, a.end, a.order, a.limit)

    def get_statistics(self, a: StatisticsArgs):
        st = self.data.statistics(a.ma_window)
        series = st.pop("moving_average")
        st["moving_average_recent"] = {"window": series["window"], "series": series["series"][-13:]}   # 토큰 절약
        return st

    def list_conversations(self, a: ListConversationsArgs):
        return self.conversations.list(a.limit)

    def get_conversation(self, a: GetConversationArgs):
        conv = self.conversations.get(a.conversation_id)
        return {"id": conv["id"], "title": conv["title"],
                "messages": [{"role": m["role"], "content": m["content"][:1500]} for m in conv.get("messages", [])[-30:]]}


def to_json(result) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
