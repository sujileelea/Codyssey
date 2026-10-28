"""미션1 수집 원본에서 시드 데이터(date, value, memo)를 만든다.

입력: ../../mission1/data/raw/trends_us_weekly.csv  (Google Trends 미국 주간, 'AI shopping' 열)
출력: data/ai_shopping_weekly.csv                      (서비스가 쓰는 시계열 261개)

- date  = 주 시작일(일요일, Google Trends 기준)
- value = 검색 관심도 지수(0~100, 기간 안 최댓값 = 100)
- memo  = 그 주에 있었던 사건 · 미션1 분석에서 찾은 급등 · 구조 단절 · 블랙프라이데이 · 최고점

    python scripts/make_seed.py
"""
import csv
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SRC = BACKEND.parent.parent / "mission1" / "data" / "raw" / "trends_us_weekly.csv"
DST = BACKEND / "data" / "ai_shopping_weekly.csv"
COLUMN = "AI shopping"

# 미션1 analysis.py 의 EVENTS_US · BLACK_FRIDAY · BREAK_WEEK 와 같은 날짜
EVENTS = [
    ("2022-11-30", "ChatGPT 공개"),
    ("2024-02-01", "Amazon Rufus 베타"),
    ("2024-07-12", "Rufus 미국 전체 공개"),
    ("2024-11-18", "Perplexity 'Buy with Pro'"),
    ("2025-04-28", "ChatGPT 검색에 쇼핑 결과"),
    ("2025-05-20", "Google I/O AI Mode 쇼핑"),
    ("2025-07-17", "ChatGPT agent"),
    ("2025-09-16", "Google AP2(에이전트 결제)"),
    ("2025-09-29", "ChatGPT Instant Checkout"),
    ("2025-11-24", "ChatGPT 쇼핑 리서치"),
]
BLACK_FRIDAY = ["2022-11-25", "2023-11-24", "2024-11-29", "2025-11-28"]
BREAK_WEEK = "2026-07-12"
# 미션1 outputs/spikes.csv — 13주 기준 z ≥ 2.5 인 급등 주
SPIKES = ["2024-11-17", "2025-06-08", "2025-06-15", "2025-06-22", "2025-07-13", "2025-07-20", "2025-11-30"]


def week_start(day: str) -> str:
    """날짜가 속한 주의 일요일(Google Trends 주 시작일)."""
    d = date.fromisoformat(day)
    return (d - timedelta(days=(d.weekday() + 1) % 7)).isoformat()


def main() -> None:
    with SRC.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["isPartial"] != "True"]   # 집계 중인 마지막 주 제외

    memos: dict[str, list[str]] = {}
    for day, name in EVENTS:
        memos.setdefault(week_start(day), []).append(f"사건: {name}")
    for day in BLACK_FRIDAY:
        memos.setdefault(week_start(day), []).append("블랙프라이데이 주")
    for day in SPIKES:
        memos.setdefault(day, []).append("급등")
    memos.setdefault(BREAK_WEEK, []).append("구조 단절: AI 관련 검색어 동시 급락(측정 변화 가설)")
    peak = max(rows, key=lambda r: int(r[COLUMN]))["date"]
    memos.setdefault(peak, []).append("최고점")

    DST.parent.mkdir(exist_ok=True)
    with DST.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value", "memo"])
        for r in rows:
            w.writerow([r["date"], int(r[COLUMN]), " · ".join(memos.get(r["date"], []))])
    print(f"{DST.relative_to(BACKEND)}: {len(rows)}행 ({rows[0]['date']} ~ {rows[-1]['date']}), memo {len(memos)}개")


if __name__ == "__main__":
    main()
