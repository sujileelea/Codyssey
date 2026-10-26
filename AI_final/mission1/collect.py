"""데이터 수집 스크립트 — 'AI 쇼핑' 검색 관심도(Google Trends) + 교차 확인용 위키백과 조회수.

실행: python collect.py            # data/raw/ 에 CSV 저장, 이미 있으면 건너뜀
      python collect.py --force    # 전부 다시 받기

Google Trends 값은 '기간 안 최댓값 = 100' 으로 정규화한 상대 지수이고, 요청마다 표본이
달라 같은 조건으로 다시 받아도 값이 조금씩 다르다. 분석은 저장된 CSV 를 기준으로 한다.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from pytrends.request import TrendReq

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw"

# 주간 데이터는 5년 이하 기간에서만 나온다(5년 초과는 월간). 종료일을 고정해 재현성을 확보한다.
WEEKLY_TF = "2021-10-24 2026-10-25"
# 일간 데이터는 269일 이하 기간에서만 나온다. 2026-07 급락 시점을 일 단위로 확인하는 용도.
DAILY_TF = "2026-05-01 2026-09-30"

TRENDS_PAYLOADS = [
    {
        "name": "trends_us_weekly",
        "role": "주 데이터 — 미국 'AI 쇼핑' 계열 검색어 5종",
        "keywords": ["AI shopping", "AI shopping assistant", "ChatGPT shopping",
                     "agentic commerce", "Amazon Rufus"],
        "geo": "US", "timeframe": WEEKLY_TF, "hl": "en-US", "tz": 300,
    },
    {
        "name": "trends_us_controls_longtail",
        "role": "대조 — 'AI shopping' 과 비슷한 규모의 비(非)AI 쇼핑 검색어",
        "keywords": ["AI shopping", "online shopping", "price comparison", "shopping list"],
        "geo": "US", "timeframe": WEEKLY_TF, "hl": "en-US", "tz": 300,
    },
    {
        "name": "trends_us_controls_highvol",
        "role": "대조 — 검색량이 큰 일반 검색어(전체 검색량 변화 확인용)",
        "keywords": ["ChatGPT", "Amazon", "weather"],
        "geo": "US", "timeframe": WEEKLY_TF, "hl": "en-US", "tz": 300,
    },
    {
        "name": "trends_kr_weekly",
        "role": "비교 — 한국 'AI 쇼핑' 단독(자체 최댓값 = 100)",
        "keywords": ["AI 쇼핑"],
        "geo": "KR", "timeframe": WEEKLY_TF, "hl": "ko", "tz": -540,
    },
    {
        "name": "trends_us_daily_2026",
        "role": "검증 — 2026-07 급락 전후 일간 값",
        "keywords": ["AI shopping", "price comparison", "online shopping"],
        "geo": "US", "timeframe": DAILY_TF, "hl": "en-US", "tz": 300,
    },
]

# 위키백과 조회수는 Google Trends 와 독립된 측정이라 급락이 '측정 문제' 인지 가리는 데 쓴다.
WIKI_ARTICLES = [
    {"name": "wiki_en_agentic_commerce", "project": "en.wikipedia", "article": "Agentic_commerce"},
    {"name": "wiki_en_online_shopping", "project": "en.wikipedia", "article": "Online_shopping"},
]
WIKI_RANGE = ("20250101", "20261025")
USER_AGENT = "codyssey-ai-final-mission1/1.0 (educational time series analysis)"

REQUEST_GAP_SEC = 20   # Google Trends 는 연속 요청에 429 를 자주 돌려준다
MAX_ATTEMPTS = 5


def fetch_trends(p: dict) -> pd.DataFrame:
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            client = TrendReq(hl=p["hl"], tz=p["tz"], timeout=(10, 30))
            client.build_payload(p["keywords"], geo=p["geo"], timeframe=p["timeframe"])
            df = client.interest_over_time()
            if df.empty:
                raise RuntimeError("빈 응답")
            df.index.name = "date"
            return df
        except Exception as e:  # 429·네트워크 오류는 대기 후 재시도
            last_err = e
            wait = 30 * attempt
            print(f"  - {p['name']} 시도 {attempt}/{MAX_ATTEMPTS} 실패({type(e).__name__}), {wait}초 대기")
            time.sleep(wait)
    raise RuntimeError(f"{p['name']} 수집 실패: {last_err}")


def fetch_wiki(w: dict) -> pd.DataFrame:
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           f"{w['project']}/all-access/user/{quote(w['article'], safe='')}/daily/"
           f"{WIKI_RANGE[0]}/{WIKI_RANGE[1]}")
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    items = r.json()["items"]
    df = pd.DataFrame({
        "date": pd.to_datetime([i["timestamp"][:8] for i in items]),
        "views": [i["views"] for i in items],
    }).set_index("date")
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 쇼핑 관심도 데이터 수집")
    parser.add_argument("--force", action="store_true", help="이미 받은 파일도 다시 받기")
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    meta_path = RAW.parent / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.setdefault("files", {})

    first = True
    for p in TRENDS_PAYLOADS:
        out = RAW / f"{p['name']}.csv"
        if out.exists() and not args.force:
            print(f"건너뜀: {out.name} (이미 있음)")
            continue
        if not first:
            time.sleep(REQUEST_GAP_SEC)
        first = False
        print(f"수집: {p['name']} {p['keywords']} geo={p['geo']} {p['timeframe']}")
        df = fetch_trends(p)
        df.to_csv(out)
        meta["files"][out.name] = {
            "source": "Google Trends (pytrends 비공식 클라이언트)",
            "role": p["role"], "keywords": p["keywords"], "geo": p["geo"],
            "timeframe": p["timeframe"], "rows": len(df),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"  -> {len(df)}행 저장")

    for w in WIKI_ARTICLES:
        out = RAW / f"{w['name']}.csv"
        if out.exists() and not args.force:
            print(f"건너뜀: {out.name} (이미 있음)")
            continue
        print(f"수집: {w['project']} {w['article']}")
        df = fetch_wiki(w)
        df.to_csv(out)
        meta["files"][out.name] = {
            "source": "Wikimedia Pageviews API (agent=user)",
            "role": "교차 확인 — Google Trends 와 독립된 관심도 측정",
            "article": f"{w['project']}/{w['article']}",
            "range": f"{WIKI_RANGE[0]}~{WIKI_RANGE[1]}", "rows": len(df),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"  -> {len(df)}행 저장")

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"메타데이터: {meta_path.relative_to(BASE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
