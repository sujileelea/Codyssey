"""서비스 객체 조립 — 라우터는 Depends 로 받기만 하고, 테스트는 이 함수들을 가짜로 바꿔 끼운다."""
from functools import lru_cache

from .firebase import get_db
from .repositories import DataRepository
from .services.data_service import DataService


@lru_cache
def get_data_service() -> DataService:
    return DataService(DataRepository(get_db()))
