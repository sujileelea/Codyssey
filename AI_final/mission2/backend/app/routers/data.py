"""/api/data — 시계열 데이터 CRUD."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query

from ..deps import get_data_service
from ..schemas import ID_PATTERN, DataIn, DataList, DataOut, Deleted
from ..services.data_service import DataService

router = APIRouter(prefix="/api/data", tags=["data"])
ItemId = Path(pattern=ID_PATTERN, description="데이터 문서 ID")


@router.post("", response_model=DataOut, status_code=201, summary="새 데이터 추가",
             responses={409: {"description": "같은 날짜가 이미 있음"}, 422: {"description": "입력 형식 오류"}})
def create_data(body: DataIn, svc: DataService = Depends(get_data_service)):
    return svc.create(body)


@router.get("", response_model=DataList, summary="데이터 목록 조회")
def list_data(
    start: date | None = Query(None, description="시작 날짜(포함)"),
    end: date | None = Query(None, description="끝 날짜(포함)"),
    order: Literal["asc", "desc"] = Query("asc", description="날짜 정렬"),
    limit: int = Query(1000, ge=1, le=1000, description="최대 개수"),
    svc: DataService = Depends(get_data_service),
):
    return svc.list(start, end, order, limit)


@router.put("/{item_id}", response_model=DataOut, summary="데이터 수정(date · value · memo 전체)",
            responses={404: {"description": "없는 ID"}, 409: {"description": "같은 날짜가 이미 있음"}})
def update_data(body: DataIn, item_id: str = ItemId, svc: DataService = Depends(get_data_service)):
    return svc.update(item_id, body)


@router.delete("/{item_id}", response_model=Deleted, summary="데이터 삭제", responses={404: {"description": "없는 ID"}})
def delete_data(item_id: str = ItemId, svc: DataService = Depends(get_data_service)):
    return svc.delete(item_id)
