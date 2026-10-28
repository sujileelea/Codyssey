"""API 오류 형식 — 모든 오류 응답을 {"detail": {"code", "message"}} 하나로 맞춘다.

프론트는 message 를 그대로 화면에 보여 주고, code 로 분기(예: 콜드스타트 재시도)한다.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from google.api_core import exceptions as gexc

log = logging.getLogger("app")

FIELD_NAMES = {"date": "날짜", "value": "값", "memo": "메모", "message": "질문", "messages": "메시지",
               "title": "제목", "role": "역할", "content": "내용", "conversation_id": "대화 ID"}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _body(code: str, message: str, **extra) -> dict:
    return {"detail": {"code": code, "message": message, **extra}}


def _field(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return " > ".join(FIELD_NAMES.get(p, p) for p in parts) or "요청"


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        errors = [{"field": _field(tuple(err.get("loc", ()))), "message": err.get("msg", "")} for err in e.errors()]
        message = "입력값을 확인해 주세요 — " + "; ".join(f"{x['field']}: {x['message']}" for x in errors)
        return JSONResponse(_body("VALIDATION_ERROR", message, errors=errors), status_code=422)

    @app.exception_handler(gexc.GoogleAPICallError)
    async def firestore_error(_: Request, e: gexc.GoogleAPICallError):
        log.warning("Firestore 오류: %s", e)
        return JSONResponse(_body("DB_UNAVAILABLE", "데이터베이스에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요."),
                            status_code=503)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, e: Exception):
        log.exception("처리하지 못한 오류")
        return JSONResponse(_body("INTERNAL", "서버 내부 오류가 발생했습니다."), status_code=500)
