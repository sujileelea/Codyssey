"""요약 · 통계 — 계산 규칙(추세 판정 · 빈 데이터 · 작은 분모)과 API 응답."""
from app.services import analysis
from conftest import weekly


def test_trend_rules():
    assert analysis.trend([10, 10, 10, 10, 12, 12, 12, 12])["direction"] == "상승"       # +20%
    assert analysis.trend([10, 10, 10, 10, 8, 8, 8, 8])["direction"] == "하락"           # -20%
    assert analysis.trend([10, 10, 10, 10, 10.4, 10.4, 10.4, 10.4])["direction"] == "유지"  # +4%
    t = analysis.trend([0, 0, 0, 0, 3, 3, 3, 3])                                          # 분모 0
    assert t["direction"] == "상승" and t["change_pct"] is None
    assert analysis.trend([5, 6, 7])["window"] == 1                                        # 개수가 적으면 창을 줄인다
    assert analysis.trend([5])["direction"] == "판단 불가"


def test_summarize_shape():
    rows = weekly([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], start="2025-12-07", memo={9: "마지막"})
    s = analysis.summarize(rows)
    assert s["period"] == "2025-12-07 ~ 2026-02-08" and s["count"] == 10
    assert s["interval"].startswith("주간")
    m = s["metrics"]
    assert (m["total"], m["average"], m["max"], m["max_date"], m["min"]) == (55, 5.5, 10, "2026-02-08", 1)
    assert s["latest"] == {"date": "2026-02-08", "value": 10, "memo": "마지막"}
    assert s["trend"].startswith("상승") and len(s["recent"]) == 8
    assert [x["month"] for x in s["monthly"]] == ["2025-12", "2026-01", "2026-02"]
    assert s["notable"] == [{"date": "2026-02-08", "value": 10, "memo": "마지막"}]


def test_empty_data():
    assert analysis.summarize([])["count"] == 0
    assert analysis.summarize([])["trend"] == "데이터 없음"
    assert analysis.statistics([])["yoy"] is None


def test_statistics():
    values = [10] * 52 + [20, 40, 30, 15]
    st = analysis.statistics(weekly(values, start="2024-01-07"), ma_window=4)
    assert st["moving_average"]["series"][2]["ma"] is None and st["moving_average"]["series"][3]["ma"] == 10
    assert st["largest_rise"]["change_pct"] == 100.0 and st["largest_drop"]["change_pct"] == -50.0
    assert st["yoy"]["year_ago_value"] == 10 and st["yoy"]["change_pct"] == 50.0
    assert st["streak"] == {"direction": "하락", "length": 2}
    assert st["from_peak_pct"] == -62.5


def test_small_base_change_is_skipped():
    st = analysis.statistics(weekly([0, 1, 0, 100, 90]))
    # 0 → 1, 1 → 0 은 분모가 0 또는 최댓값의 5% 미만이라 최대 상승/하락 후보에서 빠진다
    assert st["largest_drop"]["date"] == weekly([0] * 5)[4]["date"]
    assert st["largest_rise"] is None                                     # 남은 변화는 -10% 하나뿐


def test_summary_api(client, data_repo):
    for r in weekly([3, 4, 5, 6, 7, 8, 9, 10]):
        data_repo.create(r)
    s = client.get("/api/data/summary").json()
    assert s["count"] == 8 and s["metrics"]["average"] == 6.5 and s["trend_detail"]["direction"] == "상승"
    st = client.get("/api/data/statistics", params={"ma_window": 2}).json()
    assert st["moving_average"]["window"] == 2 and "from" in st["largest_rise"]
    assert client.get("/api/data/statistics", params={"ma_window": 1}).status_code == 422
