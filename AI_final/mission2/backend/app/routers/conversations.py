"""/api/conversations — 대화 기록.

불러오기 방식 = (A) 목록(GET /api/conversations)은 제목 · 메시지 수 · 미리보기만, 전체 messages 는
단건 조회(GET /api/conversations/{id})로 받는다.
"""
from fastapi import APIRouter, Depends, Path, Query

from ..deps import get_conversation_service
from ..schemas import ID_PATTERN, ConversationDetail, ConversationIn, ConversationList, Deleted
from ..services.conversation_service import ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
ConvId = Path(pattern=ID_PATTERN, description="대화 문서 ID")


@router.post("", response_model=ConversationDetail, status_code=201, summary="대화 저장",
             description="브라우저에만 있던 대화(자동 저장을 끈 상태)를 제목과 함께 저장한다. "
                         "/api/chat 은 기본으로 대화를 자동 저장한다.")
def create_conversation(body: ConversationIn, svc: ConversationService = Depends(get_conversation_service)):
    return svc.create(body.messages, body.title)


@router.get("", response_model=ConversationList, summary="대화 목록 조회(최근 수정 순, messages 제외)")
def list_conversations(limit: int = Query(20, ge=1, le=100, description="최대 개수"),
                       svc: ConversationService = Depends(get_conversation_service)):
    return svc.list(limit)


@router.get("/{conv_id}", response_model=ConversationDetail, summary="특정 대화 불러오기(전체 messages)",
            responses={404: {"description": "없는 ID"}})
def get_conversation(conv_id: str = ConvId, svc: ConversationService = Depends(get_conversation_service)):
    return svc.get(conv_id)


@router.delete("/{conv_id}", response_model=Deleted, summary="대화 삭제", responses={404: {"description": "없는 ID"}})
def delete_conversation(conv_id: str = ConvId, svc: ConversationService = Depends(get_conversation_service)):
    return svc.delete(conv_id)
