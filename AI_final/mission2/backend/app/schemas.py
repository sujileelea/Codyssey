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


# ── 요약 · 통계(응답) ─────────────────────────────────────

class Point(BaseModel):
    date: str
    value: float


class MemoPoint(Point):
    memo: str = ""


class Metrics(BaseModel):
    total: float
    average: float
    median: float
    std: float = Field(description="모표준편차")
    max: float
    max_date: str
    min: float
    min_date: str


class TrendDetail(BaseModel):
    direction: str = Field(description="상승 · 하락 · 유지 · 판단 불가")
    label: str
    window: int = Field(description="비교한 최근 개수 N(최근 N개 평균 vs 직전 N개 평균)")
    recent_avg: float | None
    previous_avg: float | None
    change_pct: float | None


class MonthStat(BaseModel):
    month: str
    average: float
    max: float
    min: float
    count: int


class Summary(BaseModel):
    """시스템 프롬프트에 주입하는 요약."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "period": "2021-10-24 ~ 2026-10-18", "count": 261, "interval": "주간(간격 중앙값 7일)",
        "metrics": {"total": 4213, "average": 16.14, "median": 3, "std": 25.9,
                    "max": 100, "max_date": "2026-06-07", "min": 0, "min_date": "2021-10-24"},
        "trend": "유지 (최근 4개 평균 19.75, 직전 4개 평균 20.25 대비 -2.5%)"}]})

    period: str | None
    count: int
    interval: str
    metrics: Metrics | None
    latest: MemoPoint | None
    trend: str = Field(description="단기 추세(최근 4개 평균 vs 직전 4개 평균)")
    trend_detail: TrendDetail
    trend_long: TrendDetail = Field(description="장기 추세(최근 13개 평균 vs 직전 13개 평균)")
    recent: list[Point] = Field(description="최근 8개 값")
    monthly: list[MonthStat] = Field(description="최근 12개월 월평균")
    notable: list[MemoPoint] = Field(description="메모가 있는 최근 12개 시점(사건 · 특이사항)")
    generated_at: str


class MAPoint(Point):
    ma: float | None


class MovingAverage(BaseModel):
    window: int
    series: list[MAPoint]


class YearStat(BaseModel):
    year: str
    average: float
    max: float
    min: float
    count: int
    change_pct: float | None = Field(description="전년 평균 대비(%)")


class Change(BaseModel):
    date: str
    to: float
    change_pct: float
    from_: float = Field(alias="from")


class YoY(BaseModel):
    date: str
    value: float
    year_ago_date: str
    year_ago_value: float
    change_pct: float | None


class Volatility(BaseModel):
    std_change_pct: float
    recent_std_change_pct: float
    basis: str


class Streak(BaseModel):
    direction: str
    length: int


class Statistics(BaseModel):
    """요약에 없는 추가 지표(그래프 · 도구 호출용)."""
    count: int
    moving_average: MovingAverage
    yearly: list[YearStat]
    monthly: list[MonthStat]
    yoy: YoY | None = Field(description="최신 값의 전년 같은 시기 대비")
    largest_rise: Change | None = Field(description="직전 값 대비 최대 상승")
    largest_drop: Change | None = Field(description="직전 값 대비 최대 하락")
    volatility: Volatility | None
    streak: Streak | None = Field(description="끝에서부터 같은 방향 연속 횟수")
    from_peak_pct: float | None = Field(description="최신 값의 최고점 대비(%)")
