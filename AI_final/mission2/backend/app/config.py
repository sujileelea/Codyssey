"""환경 변수 설정.

키 · 서비스 계정 값은 코드에 두지 않는다. 배포(Render)에서는 대시보드 환경 변수로,
로컬에서는 backend/.env(커밋 제외)로 받는다. 목록과 예시는 .env.example.
"""
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# 로컬 .env 가 셸 환경 변수보다 우선한다(다른 프로젝트 키가 섞여 들어오지 않게). 테스트에서는 읽지 않는다.
if os.getenv("APP_ENV") != "test":
    load_dotenv(override=True)


def _text(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = _text(name)
    return int(raw) if raw else default


def _origins(raw: str) -> list[str]:
    # 끝의 '/' 는 브라우저가 보내는 Origin 헤더와 맞지 않으므로 지운다
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    # GPT
    openai_api_key: str
    openai_model: str
    openai_base_url: str            # 비우면 OpenAI 기본 주소
    openai_max_tokens: int          # 응답 토큰 상한(과금 보호)
    openai_reasoning_effort: str    # 추론 모델용, 비우면 보내지 않음
    openai_timeout: float
    # Firebase
    firebase_service_account_json: str   # 서비스 계정 키 JSON 문자열(배포)
    firebase_service_account_path: str   # 또는 키 파일 경로(로컬)
    firebase_project_id: str
    # CORS
    allowed_origins: list[str]
    allowed_origin_regex: str
    # 호출 제한(과금 보호)
    chat_rate_per_minute: int
    chat_daily_limit: int
    # 데이터 설명(시스템 프롬프트에 함께 주입)
    dataset_name: str
    dataset_unit: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        openai_api_key=_text("OPENAI_API_KEY"),
        openai_model=_text("OPENAI_MODEL", "gpt-5.4-mini"),
        openai_base_url=_text("OPENAI_BASE_URL"),
        openai_max_tokens=_int("OPENAI_MAX_TOKENS", 1000),
        # gpt-5.4-mini 는 Chat Completions 에서 도구(Function Calling)를 쓰려면 none 이어야 한다
        openai_reasoning_effort=_text("OPENAI_REASONING_EFFORT", "none"),
        openai_timeout=float(_text("OPENAI_TIMEOUT", "40")),
        firebase_service_account_json=_text("FIREBASE_SERVICE_ACCOUNT_JSON"),
        firebase_service_account_path=_text("FIREBASE_SERVICE_ACCOUNT_PATH"),
        firebase_project_id=_text("FIREBASE_PROJECT_ID"),
        allowed_origins=_origins(_text("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")),
        allowed_origin_regex=_text("ALLOWED_ORIGIN_REGEX"),
        chat_rate_per_minute=_int("CHAT_RATE_PER_MINUTE", 10),
        chat_daily_limit=_int("CHAT_DAILY_LIMIT", 300),
        dataset_name=_text("DATASET_NAME", "미국 'AI shopping' 검색 관심도(Google Trends, 주간)"),
        dataset_unit=_text("DATASET_UNIT", "검색 관심도 지수(0~100, 기간 안 최댓값 = 100)"),
    )
