"""/api/chat — 데이터 요약을 주입한 AI 대화."""
from fastapi import APIRouter, Depends, Request

from ..deps import get_chat_service
from ..schemas import ChatIn, ChatOut, PromptPreview
from ..services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])


def client_key(request: Request) -> str:
    # Render 는 프록시 뒤라 실제 접속 주소가 X-Forwarded-For 첫 값에 온다
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@router.post("", response_model=ChatOut, summary="AI 대화(요약 주입 → GPT → 자동 저장)",
             description="① 데이터 요약 조회 → ② 요약을 시스템 프롬프트에 삽입 → ③ GPT 호출 → ④ conversations 에 저장. "
                         "conversation_id 를 주면 그 대화의 최근 10개 메시지를 함께 보내고 이어서 저장한다.",
             responses={429: {"description": "호출 제한"}, 502: {"description": "AI 오류"}, 503: {"description": "키 미설정"},
                        504: {"description": "AI 응답 지연"}})
def chat(body: ChatIn, request: Request, svc: ChatService = Depends(get_chat_service)):
    return svc.chat(body, client_key(request))


@router.get("/prompt", response_model=PromptPreview, summary="지금 주입될 시스템 프롬프트 미리 보기(GPT 호출 없음)")
def prompt_preview(svc: ChatService = Depends(get_chat_service)):
    summary, system_prompt = svc.context()
    return {"summary": summary, "system_prompt": system_prompt}
