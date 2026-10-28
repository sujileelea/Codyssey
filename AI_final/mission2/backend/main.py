"""내 데이터를 아는 AI 비서 — FastAPI 진입점.

    uvicorn main:app --reload        # 로컬, http://localhost:8000/docs

구성: main.py(앱 · CORS · 라우터 등록) → app/routers(HTTP 입출력) → app/services(규칙 · 계산 · 외부 호출)
→ app/repositories(Firestore 읽기/쓰기). 요청 검증은 app/schemas 의 Pydantic 모델이 맡는다.
"""
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import errors, firebase
from app.config import get_settings
from app.routers import conversations, data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpx2", "openai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

settings = get_settings()

app = FastAPI(
    title="내 데이터를 아는 AI 비서 API",
    description=(
        "시계열 데이터(date · value · memo)를 Firestore 에 저장하고, 요약을 시스템 프롬프트에 주입해 "
        "GPT 가 그 데이터를 근거로 답하게 하는 API.\n\n"
        f"- 데이터: {settings.dataset_name}\n"
        "- 무료 서버(Render)는 15분 동안 요청이 없으면 잠든다. 첫 요청은 30~60초 걸릴 수 있다."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "data", "description": "시계열 데이터 CRUD · 요약 · 통계"},
        {"name": "conversations", "description": "대화 기록 저장 · 목록 · 불러오기 · 삭제"},
        {"name": "chat", "description": "데이터 요약을 주입한 AI 대화(자동 저장)"},
        {"name": "system", "description": "상태 확인"},
    ],
)

# CORS — 프론트(Vercel) 주소만 허용한다. 목록은 ALLOWED_ORIGINS(쉼표 구분)로 받는다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex or None,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
errors.install(app)
app.include_router(data.router)
app.include_router(conversations.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["system"], summary="서버 상태(콜드스타트 깨우기용, DB 를 읽지 않음)")
def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "firestore_configured": firebase.is_configured(),
        "openai_configured": bool(settings.openai_api_key),
        "model": settings.openai_model,
    }
