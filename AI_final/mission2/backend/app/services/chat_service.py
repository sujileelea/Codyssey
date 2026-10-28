"""AI 대화 — 컨텍스트 주입.

흐름: ① 데이터 요약 조회(/api/data/summary 와 같은 함수) → ② 요약을 시스템 프롬프트에 삽입
→ ③ GPT 호출 → ④ 질문과 답을 conversations 에 자동 저장.

GPT 는 학습한 일반 지식만 알고 사용자의 데이터는 모른다. 매 요청마다 '지금 저장된 데이터의 요약' 을
시스템 프롬프트(대화의 전제 조건)에 글로 넣어 주면, 모델은 그 숫자를 근거로 답한다. 데이터를 고치면
다음 질문부터 바뀐 요약이 들어간다.
"""
import json
import logging
from datetime import date

from ..config import Settings
from ..errors import AppError
from .conversation_service import ConversationService
from .data_service import DataService
from .tools import TOOL_SPECS, ToolRunner, to_json

log = logging.getLogger("app.chat")

HISTORY_MESSAGES = 10    # 이전 대화는 최근 10개(5턴)만 함께 보낸다(토큰 절약)
MAX_TOOL_ROUNDS = 3      # 도구 호출 왕복 상한(과금 보호)


def fmt(x) -> str:
    """수치 표기 — 정수는 천 단위 쉼표, 소수는 둘째 자리까지."""
    if x is None:
        return "-"
    x = float(x)
    return f"{int(x):,}" if x.is_integer() else f"{x:,.2f}".rstrip("0").rstrip(".")


def build_system_prompt(summary: dict, settings: Settings, today: date | None = None, tools: bool = False) -> str:
    today = today or date.today()
    if not summary["count"]:
        data_block = "- 저장된 데이터가 없습니다. 데이터 관리 화면에서 (날짜, 값, 메모)를 추가하도록 안내하세요."
    else:
        m, latest = summary["metrics"], summary["latest"]
        recent = ", ".join(f"{p['date']}={fmt(p['value'])}" for p in summary["recent"])
        monthly = ", ".join(f"{x['month']}={fmt(x['average'])}" for x in summary["monthly"])
        notable = "\n".join(f"  - {p['date']} = {fmt(p['value'])} ({p['memo']})" for p in summary["notable"]) or "  - 없음"
        data_block = (
            f"- 데이터 기간: {summary['period']} ({summary['interval']})\n"
            f"- 총 레코드: {summary['count']}개\n"
            f"- 주요 지표: 합계 {fmt(m['total'])}, 평균 {fmt(m['average'])}, 중앙값 {fmt(m['median'])}, "
            f"표준편차 {fmt(m['std'])}, 최댓값 {fmt(m['max'])}({m['max_date']}), 최솟값 {fmt(m['min'])}({m['min_date']})\n"
            f"- 최신 값: {latest['date']} = {fmt(latest['value'])}" + (f" ({latest['memo']})" if latest["memo"] else "") + "\n"
            f"- 최근 트렌드(단기): {summary['trend']}\n"
            f"- 최근 트렌드(장기): {summary['trend_long']['label']}\n"
            f"- 최근 값: {recent}\n"
            f"- 최근 12개월 월평균: {monthly}\n"
            f"- 메모가 있는 시점:\n{notable}"
        )
    return (
        "당신은 데이터 분석 비서입니다. 사용자가 저장한 시계열 데이터를 근거로 한국어로 답합니다.\n\n"
        "[데이터 설명]\n"
        f"- 이름: {settings.dataset_name}\n"
        f"- 단위: {settings.dataset_unit}\n"
        f"- 오늘 날짜: {today.isoformat()} (데이터의 마지막 날짜와 다를 수 있음)\n\n"
        "[사용자 데이터 요약]\n"
        f"{data_block}\n\n"
        "[답변 규칙]\n"
        + ("1. 위 요약과 도구 결과의 수치를 근거로 답한다. 요약에 없는 값은 먼저 도구로 조회하고, "
           "조회해도 없을 때만 '데이터에 없는 정보' 라고 말한다. 값을 지어내지 않는다.\n" if tools else
           "1. 위 요약의 수치를 근거로 답하고, 요약에 없는 값은 지어내지 말고 '요약에 없는 정보' 라고 말한다.\n")
        + "2. 날짜와 수치를 함께 쓰고, 비교할 때는 기준(무엇 대비 몇 %)을 밝힌다. 월평균은 '월평균' 이라고 밝히고 개별 시점 값 · 최댓값과 섞지 않는다.\n"
        "3. 데이터로 확인되는 사실(관찰)과 가능한 원인 추측(해석)을 구분한다.\n"
        "4. 3~6문장으로 간결하게 답한다. 필요하면 짧은 목록을 쓴다.\n"
        "5. '이번 달' · '최근' 은 데이터의 마지막 날짜 기준으로 해석하고, 그 기준을 답에 밝힌다."
        + ("\n6. 요약에 없는 특정 기간의 값 · 연도별 비교 · 지난 대화 내용이 필요하면 도구를 호출해 확인한 뒤 답한다. "
           "'N주 전후' 처럼 범위가 정해진 질문은 앞뒤 구간이 모두 들어가도록 날짜 범위를 넉넉히 잡고(주간 데이터의 N주 = N×7일), "
           "결과가 모자라면 범위를 넓혀 다시 조회한다. 요약만으로 답할 수 있으면 도구를 부르지 않는다." if tools else "")
    )


class ChatService:
    def __init__(self, data: DataService, conversations: ConversationService, llm_factory, settings: Settings, limiter):
        self.data, self.conversations = data, conversations
        self.llm_factory = llm_factory          # 키가 없을 때 앱 시작이 아니라 채팅 요청에서 오류를 내도록 지연 생성
        self.settings, self.limiter = settings, limiter
        self.tools = ToolRunner(data, conversations)
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = self.llm_factory()
        return self._llm

    def context(self, tools: bool = False) -> tuple[dict, str]:
        summary = self.data.summary()                                        # ① 요약 조회
        return summary, build_system_prompt(summary, self.settings, tools=tools)   # ② 프롬프트에 삽입

    def chat(self, body, client: str) -> dict:
        llm = self.llm                                                        # 키가 없으면 여기서 503(호출 횟수는 세지 않음)
        self.limiter.check(client)
        summary, system_prompt = self.context(tools=body.use_tools)

        if body.conversation_id:
            history = self.conversations.get(body.conversation_id).get("messages", [])
        else:
            history = [m.model_dump() for m in body.history]
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_MESSAGES:]]
        messages.append({"role": "user", "content": body.message})

        result, used, usage = self._complete(llm, messages, body.use_tools)  # ③ GPT 호출(+ 도구)
        reply = result.content
        if not reply:
            reply = ("답변이 길어져 중간에 끊겼습니다. 질문을 더 좁혀 주세요." if result.finish_reason == "length"
                     else "답변을 만들지 못했습니다. 질문을 바꿔 다시 시도해 주세요.")

        conv_id, saved, notice = body.conversation_id, False, None
        if body.save:                                                         # ④ 자동 저장
            new = [{"role": "user", "content": body.message}, {"role": "assistant", "content": reply, "tool_calls": used}]
            try:
                if conv_id:
                    self.conversations.append(conv_id, new)
                else:
                    conv_id = self.conversations.create([*history, *new])["id"]
                saved = True
            except AppError as e:                                             # 답은 돌려주고 저장 실패만 알린다
                notice = e.message
            except Exception:
                log.exception("대화 저장 실패")
                notice = "답변은 받았지만 대화를 저장하지 못했습니다."

        return {
            "conversation_id": conv_id,
            "saved": saved,
            "notice": notice,
            "reply": reply,
            "model": llm.model,
            "tool_calls": used,
            "context": {"period": summary["period"], "count": summary["count"], "trend": summary["trend"]},
            "usage": usage or None,
        }

    def _complete(self, llm, messages: list[dict], use_tools: bool):
        """도구 호출이 끝날 때까지 GPT 와 주고받는다. 마지막 차례에는 도구를 빼서 답을 쓰게 한다."""
        used, usage = [], {}
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            tools = TOOL_SPECS if use_tools and round_no < MAX_TOOL_ROUNDS else None
            result = llm.complete(messages, tools=tools)
            for k, v in (result.usage or {}).items():
                usage[k] = usage.get(k, 0) + v
            if not result.tool_calls:
                return result, used, usage
            messages.append(result.message)
            for call in result.tool_calls:
                args = call.function.arguments
                output = self.tools.run(call.function.name, args)
                used.append({"name": call.function.name, "arguments": _args(args)})
                log.info("도구 호출 %s %s", call.function.name, args)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": to_json(output)})
        return result, used, usage


def _args(raw) -> dict:
    try:
        value = json.loads(raw or "{}") if isinstance(raw, str) else raw
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {"raw": str(raw)[:200]}
