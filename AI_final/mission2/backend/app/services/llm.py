"""GPT 호출 — openai SDK 의 Chat Completions 를 감싸고, 실패를 사용자에게 보일 오류로 바꾼다.

과금 보호: 응답 토큰 상한(OPENAI_MAX_TOKENS) · 요청 시간 제한(OPENAI_TIMEOUT) · 재시도 1회.
"""
import logging
from dataclasses import dataclass, field

import openai

from ..config import Settings
from ..errors import AppError

log = logging.getLogger("app.llm")


@dataclass
class LLMResult:
    content: str
    finish_reason: str
    tool_calls: list = field(default_factory=list)   # SDK 의 tool_call 객체(이름 · 인자 JSON 문자열 · id)
    message: dict | None = None                       # 도구 호출 이어 가기용(assistant 메시지 원형)
    usage: dict = field(default_factory=dict)


class LLMClient:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise AppError(503, "AI_NOT_CONFIGURED", "AI 키(OPENAI_API_KEY)가 설정되지 않았습니다.")
        self.settings = settings
        self.model = settings.openai_model
        self.client = openai.OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None,
                                    timeout=settings.openai_timeout, max_retries=1)

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        s = self.settings
        params = {"model": self.model, "messages": messages, "max_completion_tokens": s.openai_max_tokens}
        if s.openai_reasoning_effort:
            params["reasoning_effort"] = s.openai_reasoning_effort
        if tools:
            params["tools"] = tools
        try:
            res = self.client.chat.completions.create(**params)
        except openai.APITimeoutError as e:
            raise AppError(504, "AI_TIMEOUT", "AI 응답이 늦어 중단했습니다. 잠시 뒤 다시 시도해 주세요.") from e
        except openai.RateLimitError as e:
            if "insufficient_quota" in str(e):
                raise AppError(429, "AI_QUOTA", "AI 사용 한도를 넘었습니다. 관리자에게 문의해 주세요.") from e
            raise AppError(429, "AI_RATE_LIMITED", "AI 요청이 많습니다. 1분 뒤 다시 시도해 주세요.") from e
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            log.error("AI 인증 실패: %s", e)
            raise AppError(503, "AI_AUTH", "AI 키가 올바르지 않습니다. 관리자에게 문의해 주세요.") from e
        except openai.APIConnectionError as e:
            raise AppError(502, "AI_UNREACHABLE", "AI 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.") from e
        except openai.APIError as e:
            log.error("AI 호출 실패: %s", e)
            raise AppError(502, "AI_ERROR", "AI 응답을 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.") from e

        choice = res.choices[0]
        msg = choice.message
        usage = res.usage.model_dump(include={"prompt_tokens", "completion_tokens", "total_tokens"}) if res.usage else {}
        return LLMResult(content=(msg.content or "").strip(), finish_reason=choice.finish_reason or "",
                         tool_calls=list(msg.tool_calls or []),
                         message=msg.model_dump(include={"role", "content", "tool_calls"}, exclude_none=True),
                         usage=usage)
