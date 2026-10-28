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


def _korean(err: dict) -> str:
    """Pydantic 오류 유형 → 화면에 보일 한국어 문구(모르는 유형은 원문)."""
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    if kind == "missing":
        return "필수 항목입니다"
    if kind.startswith("date_") or kind.startswith("datetime_"):
        return "올바른 날짜(YYYY-MM-DD)가 아닙니다"
    if kind in ("float_parsing", "float_type", "int_parsing", "int_type"):
        return "숫자가 아닙니다"
    if kind == "finite_number":
        return "유한한 숫자여야 합니다"
    if kind == "string_too_long":
        return f"{ctx.get('max_length')}자 이하로 입력해 주세요"
    if kind == "string_too_short":
        return "비어 있을 수 없습니다"
    if kind == "too_short":
        return f"{ctx.get('min_length')}개 이상이어야 합니다"
    if kind == "too_long":
        return f"{ctx.get('max_length')}개 이하여야 합니다"
    if kind in ("greater_than_equal", "greater_than"):
        return f"{ctx.get('ge', ctx.get('gt'))} 이상이어야 합니다"
    if kind in ("less_than_equal", "less_than"):
        return f"{ctx.get('le', ctx.get('lt'))} 이하여야 합니다"
    if kind == "extra_forbidden":
        return "알 수 없는 항목입니다"
    if kind == "string_pattern_mismatch":
        return "형식이 올바르지 않습니다"
    if kind in ("literal_error", "enum"):
        return f"허용되는 값: {ctx.get('expected', '')}"
    if kind == "bool_parsing":
        return "true 또는 false 여야 합니다"
    if kind == "json_invalid":
        return "JSON 형식이 올바르지 않습니다"
    if kind == "value_error":
        return str(err.get("msg", "")).removeprefix("Value error, ")
    return err.get("msg", "")


def _field(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return " > ".join(FIELD_NAMES.get(p, p) for p in parts) or "요청"


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        errors = [{"field": _field(tuple(err.get("loc", ()))), "message": _korean(err), "type": err.get("type")}
                  for err in e.errors()]
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
