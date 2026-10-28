"""서비스 객체 조립 — 라우터는 Depends 로 받기만 하고, 테스트는 이 함수들을 가짜로 바꿔 끼운다."""
from functools import lru_cache

from .config import get_settings
from .firebase import get_db
from .repositories import ConversationRepository, DataRepository
from .services.chat_service import ChatService
from .services.conversation_service import ConversationService
from .services.data_service import DataService
from .services.llm import LLMClient
from .services.rate_limit import RateLimiter


@lru_cache
def get_data_service() -> DataService:
    return DataService(DataRepository(get_db()))


@lru_cache
def get_conversation_service() -> ConversationService:
    return ConversationService(ConversationRepository(get_db()))


@lru_cache
def get_rate_limiter() -> RateLimiter:
    s = get_settings()
    return RateLimiter(s.chat_rate_per_minute, s.chat_daily_limit)


@lru_cache
def get_chat_service() -> ChatService:
    s = get_settings()
    return ChatService(get_data_service(), get_conversation_service(), lambda: LLMClient(s), s, get_rate_limiter())
