"""요청 · 응답 모델(Pydantic).

요청 모델은 들어오는 값을 라우터에 닿기 전에 검증한다 — 형식이 틀리면 422 와 필드별 이유를 돌려주고,
서비스 코드는 '이미 검증된 값' 만 다룬다. extra="forbid" 로 오타 난 필드도 거른다.
"""
from datetime import date as Date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"   # Firestore 문서 ID(자동 생성 20자)와 같은 문자만


class _In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# ── 데이터 ────────────────────────────────────────────────

class DataIn(_In):
    """POST · PUT 본문. PUT 은 세 필드를 모두 보내 통째로 바꾼다."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"date": "2026-10-25", "value": 17, "memo": "직접 추가한 주"}]})

    date: Date = Field(description="날짜(YYYY-MM-DD). 같은 날짜는 하나만 둔다.")
    value: float = Field(ge=-1_000_000_000, le=1_000_000_000, allow_inf_nan=False, description="값")
    memo: str = Field("", max_length=200, description="메모(사건 · 특이사항, 200자 이하)")

    @field_validator("date")
    @classmethod
    def _date_range(cls, v: Date) -> Date:
        if v < Date(2000, 1, 1) or v > Date.today() + timedelta(days=366):
            raise ValueError("2000-01-01 부터 1년 뒤까지의 날짜만 받습니다")
        return v


class DataOut(BaseModel):
    id: str
    date: str
    value: float
    memo: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DataList(BaseModel):
    count: int = Field(description="응답에 담긴 개수")
    total: int = Field(description="조건과 무관한 전체 개수")
    items: list[DataOut]


class Deleted(BaseModel):
    id: str
    deleted: bool = True
