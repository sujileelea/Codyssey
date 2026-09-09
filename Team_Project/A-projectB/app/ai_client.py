"""AI API 공용 클라이언트 (담당: 경학 · 요약용 generate_text 추가: 진성/owner).

- provider `gemini`: Google Gemini Developer API (`google-genai` SDK). 무료 티어.
- provider `mock`: API 키 없이 파이프라인을 점검하는 개발용.
API 키는 코드·config.json에 두지 않고 환경변수(`.env`)에서 읽는다. 키 검사는 호출 시점에만 한다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

logger = logging.getLogger(__name__)


INSIGHT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "trends": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 6,
            "maxItems": 6,
        },
        "major_issues": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 4,
            "maxItems": 4,
        },
    },
    "required": ["trends", "keywords", "major_issues"],
    "additionalProperties": False,
}

SENTIMENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative"],
        },
        "score": {
            "type": "number",
            "minimum": -1.0,
            "maximum": 1.0,
        },
        "reason": {"type": "string"},
    },
    "required": ["sentiment", "score", "reason"],
    "additionalProperties": False,
}


class AIClient(ABC):
    @abstractmethod
    def generate_insight(self, instructions: str, prompt: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def generate_sentiment(self, instructions: str, prompt: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def generate_text(self, instructions: str, prompt: str, max_output_tokens: int | None = None) -> str:
        """자유 텍스트 응답 (뉴스 요약용)."""
        raise NotImplementedError


class GeminiClient(AIClient):
    """Google Gemini Developer API client.

    API 키는 코드/config.json에 직접 저장하지 않고 환경변수에서 읽는다.
    """

    def __init__(self, ai_config: dict):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai 패키지가 필요합니다. pip install -r requirements.txt"
            ) from exc

        api_key_env = ai_config.get("api_key_env", "GEMINI_API_KEY")
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise RuntimeError(f"환경변수 {api_key_env}에 Gemini API 키가 설정되어 있지 않습니다.")

        timeout_ms = int(float(ai_config.get("timeout", 60)) * 1000)
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
        self.types = types
        self.model = ai_config.get("model", "gemini-3.5-flash-lite")
        self.max_output_tokens = int(ai_config.get("max_output_tokens", 1800))
        # 무료 티어 분당 요청 한도(RPM)를 지키기 위한 최소 호출 간격과 429 대기 재시도
        self.min_interval = float(ai_config.get("min_interval_seconds", 4.5))
        self.rate_limit_retries = int(ai_config.get("rate_limit_retries", 3))
        self._last_call_at = 0.0

    def _call(self, fn: Callable[[], Any]) -> Any:
        """호출 간격을 지키고, 429(RESOURCE_EXHAUSTED)면 서버가 알려준 시간만큼 기다렸다가 재시도한다."""
        for attempt in range(self.rate_limit_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_call_at)
            if wait > 0:
                time.sleep(wait)
            self._last_call_at = time.monotonic()
            try:
                return fn()
            except Exception as error:
                text = str(error)
                if "RESOURCE_EXHAUSTED" not in text and "429" not in text:
                    raise
                if attempt >= self.rate_limit_retries:
                    raise
                match = re.search(r"retry in (\d+(?:\.\d+)?)s", text, re.IGNORECASE)
                delay = float(match.group(1)) + 1.0 if match else 30.0
                logger.warning("Gemini 무료 티어 한도(429) → %.0f초 대기 후 재시도 (%s/%s)", delay, attempt + 1, self.rate_limit_retries)
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def _generate_json(
        self,
        instructions: str,
        prompt: str,
        schema: dict[str, Any],
        max_output_tokens: int | None = None,
    ) -> dict:
        response = self._call(
            lambda: self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    system_instruction=instructions,
                    max_output_tokens=max_output_tokens or self.max_output_tokens,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    automatic_function_calling=self.types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        )
        if not response.text:
            raise RuntimeError("Gemini가 텍스트 응답을 반환하지 않았습니다.")
        return json.loads(response.text)

    def generate_insight(self, instructions: str, prompt: str) -> dict:
        return self._generate_json(instructions, prompt, INSIGHT_JSON_SCHEMA)

    def generate_sentiment(self, instructions: str, prompt: str) -> dict:
        return self._generate_json(
            instructions,
            prompt,
            SENTIMENT_JSON_SCHEMA,
            max_output_tokens=min(self.max_output_tokens, 500),
        )

    def generate_text(self, instructions: str, prompt: str, max_output_tokens: int | None = None) -> str:
        response = self._call(
            lambda: self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    system_instruction=instructions,
                    max_output_tokens=max_output_tokens or self.max_output_tokens,
                    automatic_function_calling=self.types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        )
        if not response.text:
            raise RuntimeError("Gemini가 텍스트 응답을 반환하지 않았습니다.")
        return response.text.strip()


class MockAIClient(AIClient):
    """API 키 없이 파이프라인과 DB 저장을 점검하기 위한 개발용 클라이언트."""

    def generate_insight(self, instructions: str, prompt: str) -> dict:
        return {
            "trends": [
                "테스트 트렌드 1",
                "테스트 트렌드 2",
                "테스트 트렌드 3",
            ],
            "keywords": [
                "테스트키워드1",
                "테스트키워드2",
                "테스트키워드3",
                "테스트키워드4",
                "테스트키워드5",
                "테스트키워드6",
            ],
            "major_issues": [
                "테스트 주요 이슈 1",
                "테스트 주요 이슈 2",
                "테스트 주요 이슈 3",
                "테스트 주요 이슈 4",
            ],
        }

    def generate_sentiment(self, instructions: str, prompt: str) -> dict:
        return {
            "sentiment": "neutral",
            "score": 0.0,
            "reason": "테스트용 중립 감성 결과",
        }

    def generate_text(self, instructions: str, prompt: str, max_output_tokens: int | None = None) -> str:
        return "테스트용 요약 문장 1. 테스트용 요약 문장 2. 테스트용 요약 문장 3."


def build_ai_client(ai_config: dict) -> AIClient:
    provider = ai_config.get("provider", "gemini").lower()
    if provider == "gemini":
        return GeminiClient(ai_config)
    if provider == "mock":
        return MockAIClient()
    raise ValueError(f"지원하지 않는 AI provider입니다: {provider}")
