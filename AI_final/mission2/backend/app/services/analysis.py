"""시계열 분석 — 데이터 목록을 받아 요약 · 통계를 계산하는 순수 함수(입출력 없음).

요약(summarize)은 시스템 프롬프트에 주입할 '짧은 사실 묶음' 이고, 통계(statistics)는 화면 그래프와
도구 호출(Function Calling)이 쓰는 '자세한 지표' 다. 입력은 날짜 오름차순 [{date, value, memo}].
"""
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median, pstdev

TREND_WINDOW = 4          # 최근 N개 평균 vs 직전 N개 평균(단기)
LONG_WINDOW = 13          # 장기(주간이면 한 분기)
TREND_THRESHOLD = 5.0     # ±5% 안이면 '유지'
SMALL_BASE_RATIO = 0.05   # 변화율 분모가 최댓값의 5% 미만이면 계산하지 않음(0 → 1 이 +∞% 가 되는 것 방지)


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def _pct(new: float, old: float, min_base: float = 0.0) -> float | None:
    if old == 0 or abs(old) < min_base:
        return None
    return (new - old) / abs(old) * 100


def _interval(points: list[dict]) -> str:
    if len(points) < 2:
        return "-"
    days = [(date.fromisoformat(b["date"]) - date.fromisoformat(a["date"])).days for a, b in zip(points, points[1:])]
    gap = median(days)
    for limit, name in ((1, "일간"), (7, "주간"), (31, "월간")):
        if gap <= limit:
            return f"{name}(간격 중앙값 {gap:g}일)"
    return f"불규칙(간격 중앙값 {gap:g}일)"


def trend(values: list[float], window: int = TREND_WINDOW) -> dict:
    """최근 window 개 평균을 직전 window 개 평균과 비교해 상승 · 하락 · 유지로 판정."""
    if len(values) < 2:
        return {"direction": "판단 불가", "label": "판단 불가(데이터 2개 미만)", "window": 0,
                "recent_avg": None, "previous_avg": None, "change_pct": None}
    w = min(window, len(values) // 2)
    recent, previous = mean(values[-w:]), mean(values[-2 * w:-w])
    change = _pct(recent, previous)
    if change is None:
        direction = "상승" if recent > previous else "하락" if recent < previous else "유지"
    else:
        direction = "상승" if change > TREND_THRESHOLD else "하락" if change < -TREND_THRESHOLD else "유지"
    detail = f"최근 {w}개 평균 {_r(recent):g}, 직전 {w}개 평균 {_r(previous):g}" + (f" 대비 {change:+.1f}%" if change is not None else "")
    return {"direction": direction, "label": f"{direction} ({detail})", "window": w,
            "recent_avg": _r(recent), "previous_avg": _r(previous), "change_pct": _r(change, 1)}


def monthly(points: list[dict]) -> list[dict]:
    groups: dict[str, list[float]] = {}
    for p in points:
        groups.setdefault(p["date"][:7], []).append(p["value"])
    return [{"month": m, "average": _r(mean(v)), "max": max(v), "min": min(v), "count": len(v)}
            for m, v in sorted(groups.items())]


def summarize(points: list[dict]) -> dict:
    """프롬프트 주입용 요약 — 기간 · 개수 · 기본 통계 · 최근 추세 + 답변 근거가 되는 최근 값 · 월평균 · 메모."""
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not points:
        return {"period": None, "count": 0, "interval": "-", "metrics": None, "latest": None,
                "trend": "데이터 없음", "trend_detail": trend([]), "trend_long": trend([]),
                "recent": [], "monthly": [], "notable": [],
                "generated_at": generated}
    values = [p["value"] for p in points]
    hi = max(points, key=lambda p: p["value"])
    lo = min(points, key=lambda p: p["value"])
    t = trend(values)
    long = trend(values, LONG_WINDOW)
    last = points[-1]
    return {
        "period": f"{points[0]['date']} ~ {last['date']}",
        "count": len(points),
        "interval": _interval(points),
        "metrics": {
            "total": _r(sum(values)),
            "average": _r(mean(values)),
            "median": _r(median(values)),
            "std": _r(pstdev(values)),
            "max": hi["value"], "max_date": hi["date"],
            "min": lo["value"], "min_date": lo["date"],
        },
        "latest": {"date": last["date"], "value": last["value"], "memo": last.get("memo", "")},
        "trend": t["label"],
        "trend_detail": t,
        "trend_long": long,
        "recent": [{"date": p["date"], "value": p["value"]} for p in points[-8:]],
        "monthly": monthly(points)[-12:],
        "notable": [{"date": p["date"], "value": p["value"], "memo": p["memo"]} for p in points if p.get("memo")][-12:],
        "generated_at": generated,
    }


def _nearest(points: list[dict], target: date, tolerance_days: int) -> dict | None:
    best = min(points, key=lambda p: abs((date.fromisoformat(p["date"]) - target).days), default=None)
    if best and abs((date.fromisoformat(best["date"]) - target).days) <= tolerance_days:
        return best
    return None


def moving_average(values: list[float], window: int) -> list[float | None]:
    """직전 window 개 평균(그 시점까지의 값만 사용). 앞쪽 window-1 개는 None."""
    out: list[float | None] = []
    for i in range(len(values)):
        out.append(_r(mean(values[i - window + 1:i + 1])) if i >= window - 1 else None)
    return out


def statistics(points: list[dict], ma_window: int = 4) -> dict:
    """요약에 없는 추가 지표 — 이동평균 · 연도별 · 전년 동기 대비 · 최대 상승/하락 · 변동성 · 연속 방향 · 최고점 대비."""
    if not points:
        return {"count": 0, "moving_average": {"window": ma_window, "series": []}, "yearly": [], "monthly": [],
                "yoy": None, "largest_rise": None, "largest_drop": None, "volatility": None,
                "streak": None, "from_peak_pct": None}
    values = [p["value"] for p in points]
    ma = moving_average(values, ma_window)
    min_base = max(abs(v) for v in values) * SMALL_BASE_RATIO

    # 연도별 평균과 전년 대비
    years: dict[str, list[float]] = {}
    for p in points:
        years.setdefault(p["date"][:4], []).append(p["value"])
    year_avgs = {y: mean(v) for y, v in years.items()}
    year_base = max(abs(a) for a in year_avgs.values()) * SMALL_BASE_RATIO
    yearly, prev = [], None
    for y, v in sorted(years.items()):
        avg = year_avgs[y]
        yearly.append({"year": y, "average": _r(avg), "max": max(v), "min": min(v), "count": len(v),
                       "change_pct": _r(_pct(avg, prev, year_base), 1) if prev is not None else None})
        prev = avg

    # 직전 값 대비 변화율 — 최대 상승 · 하락, 변동성(변화율 표준편차)
    changes = []
    for a, b in zip(points, points[1:]):
        pct = _pct(b["value"], a["value"], min_base)
        if pct is not None:
            changes.append({"date": b["date"], "from": a["value"], "to": b["value"], "change_pct": _r(pct, 1)})
    rise = max((c for c in changes if c["change_pct"] > 0), key=lambda c: c["change_pct"], default=None)
    drop = min((c for c in changes if c["change_pct"] < 0), key=lambda c: c["change_pct"], default=None)
    pcts = [c["change_pct"] for c in changes]
    volatility = {"std_change_pct": _r(pstdev(pcts), 1), "recent_std_change_pct": _r(pstdev(pcts[-13:]), 1),
                  "basis": "직전 값 대비 변화율의 표준편차(전체 · 최근 13개)"} if len(pcts) >= 2 else None

    # 전년 같은 시기 대비(±7일 안에서 가장 가까운 날짜)
    last = points[-1]
    year_ago = _nearest(points, date.fromisoformat(last["date"]) - timedelta(days=364), 7)
    yoy = None
    if year_ago:
        yoy = {"date": last["date"], "value": last["value"], "year_ago_date": year_ago["date"],
               "year_ago_value": year_ago["value"], "change_pct": _r(_pct(last["value"], year_ago["value"], min_base), 1)}

    # 끝에서부터 같은 방향으로 몇 번 연속 움직였나
    streak = None
    if len(values) >= 2 and values[-1] != values[-2]:
        up = values[-1] > values[-2]
        n = 0
        for a, b in zip(reversed(values[:-1]), reversed(values)):
            if (b > a) if up else (b < a):
                n += 1
            else:
                break
        streak = {"direction": "상승" if up else "하락", "length": n}

    peak = max(values)
    return {
        "count": len(points),
        "moving_average": {"window": ma_window,
                           "series": [{"date": p["date"], "value": p["value"], "ma": m} for p, m in zip(points, ma)]},
        "yearly": yearly,
        "monthly": monthly(points),
        "yoy": yoy,
        "largest_rise": rise,
        "largest_drop": drop,
        "volatility": volatility,
        "streak": streak,
        "from_peak_pct": _r(_pct(last["value"], peak), 1),
    }
