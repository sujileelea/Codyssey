"""'AI 쇼핑' 검색 관심도 시계열 분석 — 정제 · 분석 · 시각화.

실행: python analysis.py   (먼저 python collect.py 로 data/raw/ 를 채운다)
출력: images/*.png(그림 9장) · outputs/*.csv(표) · outputs/key_numbers.json(리포트 수치)
      data/processed/us_weekly_clean.csv(정제한 주 데이터 + 파생 지표)
"""

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

warnings.filterwarnings("ignore", category=FutureWarning)

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw"
PROCESSED = BASE / "data" / "processed"
IMAGES = BASE / "images"
OUTPUTS = BASE / "outputs"

MAIN = "AI shopping"
KR = "AI 쇼핑"

# 2026-07-12 주에 AI 관련 검색어가 함께 꺾인다. 그 주를 전환 주로 빼고 앞뒤를 비교한다.
PRE = ("2026-05-03", "2026-07-05")     # 급락 전 10주
BREAK_WEEK = "2026-07-12"
POST = ("2026-07-19", "2026-10-18")    # 급락 후 14주(마지막 완결 주까지)
PRE_LAST = "2026-07-05"                # 추세·분해·예측 검증은 이 주까지만 쓴다

# 외부 사건(공식 발표·주요 보도로 날짜 확인). 그래프에는 번호로 표시한다.
EVENTS_US = [
    ("2022-11-30", "ChatGPT 공개"),
    ("2024-02-01", "Amazon Rufus 베타"),
    ("2024-07-12", "Rufus 미국 전체 공개"),
    ("2024-11-18", "Perplexity 'Buy with Pro'"),
    ("2025-04-28", "ChatGPT 검색에 쇼핑 결과"),
    ("2025-05-20", "Google I/O — AI Mode 쇼핑"),
    ("2025-07-17", "ChatGPT agent"),
    ("2025-09-16", "Google AP2(에이전트 결제)"),
    ("2025-09-29", "ChatGPT Instant Checkout"),
    ("2025-11-24", "ChatGPT 쇼핑 리서치"),
]
EVENTS_KR = [
    ("2025-03-12", "네이버플러스 스토어 앱(AI 쇼핑 가이드)"),
    ("2026-02-26", "네이버 쇼핑 AI 에이전트 베타"),
]
BLACK_FRIDAY = ["2022-11-25", "2023-11-24", "2024-11-29", "2025-11-28"]
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

# 차트 색 — 범주 색은 정해진 순서대로만 쓴다(검증 스크립트로 인접 쌍 색각 구분 확인).
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
       "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb", "wash": "#f0efec"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
POS, NEG = "#2a78d6", "#e34948"   # 증감(양극) 표현용 파랑↔빨강


# ---------------------------------------------------------------- 공통

def setup_style() -> None:
    available = {f.name for f in fm.fontManager.ttflist}
    family = next((f for f in ["Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic",
                               "NanumGothic", "Noto Sans CJK KR"] if f in available), "DejaVu Sans")
    plt.rcParams.update({
        "font.family": family, "axes.unicode_minus": False,
        "figure.facecolor": INK["surface"], "axes.facecolor": INK["surface"],
        "savefig.facecolor": INK["surface"], "figure.dpi": 100, "savefig.dpi": 150,
        "axes.edgecolor": INK["axis"], "axes.linewidth": 0.8,
        "axes.labelcolor": INK["secondary"], "axes.titlecolor": INK["secondary"],
        "xtick.color": INK["muted"], "ytick.color": INK["muted"],
        "xtick.labelcolor": INK["secondary"], "ytick.labelcolor": INK["secondary"],
        "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.labelsize": 9.5,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": INK["grid"],
        "grid.linewidth": 0.8, "grid.linestyle": "-",
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 1.6,
        "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
    })


def new_fig(nrows=1, ncols=1, height=5.2, **kw):
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, height), layout="constrained", **kw)
    return fig, axes


def finish(fig, axes_top, title, subtitle, source, filename):
    fig.suptitle(title, x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK["primary"])
    axes_top.set_title(subtitle, loc="left", fontsize=9.5, color=INK["secondary"], pad=10)
    fig.supxlabel(source, x=0.01, ha="left", fontsize=8, color=INK["muted"])
    fig.savefig(IMAGES / filename)
    plt.close(fig)
    print(f"  그림 저장: images/{filename}")


def date_axis(ax, minor_quarters=True):
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    if minor_quarters:
        ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))


def week_of(date: str) -> pd.Timestamp:
    """날짜가 속한 Google Trends 주(일요일 시작)."""
    d = pd.Timestamp(date)
    return d - pd.Timedelta(days=(d.day_of_week + 1) % 7)


def mark_events(ax, events, y=None, color=None, step=7):
    top = ax.get_ylim()[1] if y is None else y
    prev, level = None, 0
    for i, (d, _) in enumerate(events):
        x = pd.Timestamp(d)
        if not (ax.get_xlim()[0] <= mdates.date2num(x) <= ax.get_xlim()[1]):
            continue
        # 6주 안에 이어진 사건은 번호를 한 칸 내려 겹치지 않게 한다
        level = (level + 1) % 2 if prev is not None and (x - prev).days < 42 else 0
        prev = x
        ax.axvline(x, color=color or INK["axis"], lw=0.8, zorder=0)
        ax.text(x, top - level * step, CIRCLED[i], ha="center", va="top", fontsize=10, color=INK["secondary"],
                bbox=dict(boxstyle="circle,pad=0.1", fc=INK["surface"], ec="none"))


def mark_break(ax, label=True, y_frac=0.97):
    ax.axvspan(pd.Timestamp(PRE_LAST), pd.Timestamp(POST[0]), color=INK["wash"], zorder=0, lw=0)
    if label:
        ax.text(pd.Timestamp(POST[0]) + pd.Timedelta(days=5), ax.get_ylim()[1] * y_frac,
                "단절 의심\n(2026-07-12 주)", fontsize=8, color=INK["muted"], va="top")


def end_label(ax, x, y, text, dy=0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points", fontsize=8.5,
                color=INK["secondary"], va="center")


def rolling_by_segment(x, window, **kw):
    """이동평균이 구조 단절(2026-07-12 주)을 넘지 않게 앞뒤 구간을 따로 계산한다.
    가운데 정렬 창이 단절을 넘으면 단절 전 몇 주에 단절 후의 낮은 값이 섞여 추세가 왜곡된다."""
    return pd.concat([part.rolling(window, **kw).mean() for part in (x[:PRE_LAST], x[BREAK_WEEK:])])


def event_key(events, per_line=5):
    items = [f"{CIRCLED[i]} {name}" for i, (_, name) in enumerate(events)]
    return "\n".join("  ".join(items[i:i + per_line]) for i in range(0, len(items), per_line))


# ---------------------------------------------------------------- 1. 적재·정제

def load_trends(name):
    df = pd.read_csv(RAW / f"{name}.csv", index_col="date", parse_dates=True)
    partial = df.index[df["isPartial"]].strftime("%Y-%m-%d").tolist()
    return df.loc[~df["isPartial"]].drop(columns="isPartial"), partial


def load_wiki_weekly(name):
    """일별 조회수 → Google Trends 와 같은 일요일 시작 주로 합산(7일이 다 찬 주만)."""
    daily = pd.read_csv(RAW / f"{name}.csv", index_col="date", parse_dates=True)["views"]
    weekly = daily.resample("W-SAT").agg(["sum", "count"])
    weekly.index = weekly.index - pd.Timedelta(days=6)
    return weekly.loc[weekly["count"] == 7, "sum"], daily


def quality_row(name, df, partial, step):
    full = pd.date_range(df.index.min(), df.index.max(), freq=step)
    return {
        "file": name, "rows": len(df), "start": df.index.min().date(), "end": df.index.max().date(),
        "missing_dates": len(full.difference(df.index)), "nan_cells": int(df.isna().sum().sum()),
        "zero_cells": int((df == 0).sum().sum()), "partial_rows_removed": ", ".join(partial) or "-",
    }


def load_all():
    data, quality = {}, []
    for name in ["trends_us_weekly", "trends_us_controls_longtail", "trends_us_controls_highvol",
                 "trends_kr_weekly"]:
        df, partial = load_trends(name)
        data[name] = df
        quality.append(quality_row(name, df, partial, "7D"))
    daily, partial = load_trends("trends_us_daily_2026")
    data["daily"] = daily
    quality.append(quality_row("trends_us_daily_2026", daily, partial, "D"))
    for name in ["wiki_en_agentic_commerce", "wiki_en_online_shopping"]:
        weekly, raw_daily = load_wiki_weekly(name)
        data[name] = weekly
        quality.append(quality_row(name, raw_daily.to_frame(), [], "D"))
    q = pd.DataFrame(quality)
    q.to_csv(OUTPUTS / "data_quality.csv", index=False)
    print("데이터 품질 점검")
    print(q.to_string(index=False))
    return data


# ---------------------------------------------------------------- 2. 파생 지표

def build_features(us: pd.DataFrame) -> pd.DataFrame:
    s = us[MAIN]
    f = pd.DataFrame({MAIN: s})
    f["ma4"] = rolling_by_segment(s, 4, center=True, min_periods=3)     # 한 달 흐름(가운데 정렬)
    f["ma13"] = rolling_by_segment(s, 13, center=True, min_periods=7)   # 한 분기 흐름(가운데 정렬)
    prev = s.shift(1)
    # 0 은 '검색량이 임계값 미만' 이라 변화율의 분모로 쓰지 않는다(분모 5 이상만 계산).
    f["wow_pct"] = np.where(prev >= 5, (s / prev - 1) * 100, np.nan)
    trailing4 = s.rolling(4).mean()
    f["yoy_ratio_4w"] = np.where(trailing4.shift(52) >= 1, trailing4 / trailing4.shift(52), np.nan)
    # 변동성: 주간 로그 변화율의 13주 표준편차(수준과 무관하게 '주마다 얼마나 출렁이나'). 값 5 미만 구간은 제외.
    logchg = np.log((s / prev).where((s >= 5) & (prev >= 5)))   # 조건을 먼저 걸어 log(0) 경고를 막는다
    f["vol13"] = logchg.rolling(13, min_periods=8).std() * 100
    # 급등 탐지: 직전 8주 중앙값 대비 로그 비율을 로버스트 z 점수로 바꾼다(2023년 이후만).
    base = s.shift(1).rolling(8).median()
    lr = np.log((s + 1) / (base + 1))
    ref = lr["2023-01-01":PRE_LAST]
    mad = (ref - ref.median()).abs().median() * 1.4826
    f["spike_z"] = (lr - ref.median()) / mad
    f.loc[:"2022-12-31", "spike_z"] = np.nan
    return f


# ---------------------------------------------------------------- 3. 분석 표

def phase_table(s: pd.Series) -> pd.DataFrame:
    phases = [
        ("P0 ChatGPT 이전", "2021-10-24", "2022-11-27"),
        ("P1 생성형 AI 확산", "2022-12-04", "2024-12-29"),
        ("P2 쇼핑 기능 출시기", "2025-01-05", "2025-06-29"),
        ("P3 고점기", "2025-07-06", "2026-07-05"),
        ("P4 급락 이후", "2026-07-12", "2026-10-18"),
    ]
    rows = []
    for name, a, b in phases:
        x = s[a:b]
        rows.append({"구간": name, "시작": a, "끝": b, "주수": len(x), "평균": x.mean(),
                     "중앙값": x.median(), "표준편차": x.std(), "변동계수": x.std() / x.mean() if x.mean() else np.nan,
                     "최대": x.max(), "0인 주 비율(%)": (x == 0).mean() * 100})
    return pd.DataFrame(rows).round(2)


def event_table(s: pd.Series, events, before=4, after=4) -> pd.DataFrame:
    rows = []
    for i, (d, name) in enumerate(events):
        w = week_of(d)
        b = s[w - pd.Timedelta(weeks=before): w - pd.Timedelta(weeks=1)]
        a = s[w: w + pd.Timedelta(weeks=after - 1)]
        rows.append({"번호": CIRCLED[i], "날짜": d, "사건": name, f"직전{before}주 평균": b.mean(),
                     f"이후{after}주 평균": a.mean(),
                     "변화율(%)": (a.mean() / b.mean() - 1) * 100 if b.mean() >= 1 else np.nan})
    return pd.DataFrame(rows).round(1)


def black_friday_table(series: dict) -> pd.DataFrame:
    rows = []
    for d in BLACK_FRIDAY:
        w = week_of(d)
        row = {"블랙프라이데이": d, "주(일요일 시작)": w.date()}
        for label, s in series.items():
            base = s[w - pd.Timedelta(weeks=4): w - pd.Timedelta(weeks=1)].mean()
            row[f"{label} 배수"] = round(s[w] / base, 2) if base >= 1 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def takeoff(s: pd.Series, level: float):
    ma = rolling_by_segment(s, 4, center=True, min_periods=3)   # 그림 07 과 같은 이동평균
    hit = ma[ma >= level]
    return hit.index[0] if len(hit) else None


def doubling_weeks(ma: pd.Series, a: str, b: str):
    x = ma[a:b].dropna()
    x = x[x > 0]
    t = np.arange(len(x))
    slope = np.polyfit(t, np.log(x.values), 1)[0]
    return (np.log(2) / slope if slope > 0 else np.nan), slope


def break_table(data) -> pd.DataFrame:
    us, lt, hv, kr = (data["trends_us_weekly"], data["trends_us_controls_longtail"],
                      data["trends_us_controls_highvol"], data["trends_kr_weekly"])
    items = [
        ("AI 관련", "AI shopping (미국)", us[MAIN]),
        ("AI 관련", "AI shopping assistant", us["AI shopping assistant"]),
        ("AI 관련", "ChatGPT shopping", us["ChatGPT shopping"]),
        ("AI 관련", "agentic commerce", us["agentic commerce"]),
        ("AI 관련", "Amazon Rufus", us["Amazon Rufus"]),
        ("AI 관련", "AI 쇼핑 (한국)", kr[KR]),
        ("위키백과 조회수", "Agentic commerce 문서", data["wiki_en_agentic_commerce"]),
        ("위키백과 조회수", "Online shopping 문서", data["wiki_en_online_shopping"]),
        ("비AI 쇼핑 검색어", "price comparison", lt["price comparison"]),
        ("비AI 쇼핑 검색어", "online shopping", lt["online shopping"]),
        ("비AI 쇼핑 검색어", "shopping list", lt["shopping list"]),
        ("대형 일반 검색어", "ChatGPT", hv["ChatGPT"]),
        ("대형 일반 검색어", "Amazon", hv["Amazon"]),
        ("대형 일반 검색어", "weather", hv["weather"]),
    ]
    rows = []
    for group, label, s in items:
        pre, post = s[PRE[0]:PRE[1]], s[POST[0]:POST[1]]
        # 계절 기준선: 1년 전 같은 주 구간의 변화(데이터가 있을 때만)
        p0 = s[(pd.Timestamp(PRE[0]) - pd.Timedelta(weeks=52)):(pd.Timestamp(PRE[1]) - pd.Timedelta(weeks=52))]
        q0 = s[(pd.Timestamp(POST[0]) - pd.Timedelta(weeks=52)):(pd.Timestamp(POST[1]) - pd.Timedelta(weeks=52))]
        last_year = (q0.mean() / p0.mean() - 1) * 100 if len(p0) >= 8 and p0.mean() >= 1 else np.nan
        rows.append({"묶음": group, "계열": label, "급락 전 평균": pre.mean(), "급락 후 평균": post.mean(),
                     "변화율(%)": (post.mean() / pre.mean() - 1) * 100,
                     "1년 전 같은 구간 변화율(%)": last_year})
    return pd.DataFrame(rows).round(1)


# ---------------------------------------------------------------- 4. 그림

def fig01_trend(f, numbers):
    fig, (ax1, ax2) = new_fig(2, 1, height=7.4, sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    s = f[MAIN]
    ax1.plot(s.index, s, color=SERIES[0], lw=0.9, alpha=0.35, label="주간 원값")
    ax1.plot(f.index, f["ma4"], color=SERIES[0], lw=1.6, alpha=0.7, label="4주 이동평균")
    ax1.plot(f.index, f["ma13"], color=SERIES[0], lw=2.4, label="13주 이동평균")
    ax1.set_ylim(0, 114)
    ax1.set_yticks([0, 20, 40, 60, 80, 100])
    ax1.set_ylabel("검색 관심도 (기간 최댓값=100)")
    mark_break(ax1, y_frac=0.62)
    mark_events(ax1, EVENTS_US, y=113)
    peak = s.idxmax()
    ax1.annotate(f"최고 100 ({peak:%Y-%m-%d} 주)", (peak, 100), xytext=(14, -2), textcoords="offset points",
                 fontsize=8.5, color=INK["secondary"], va="center",
                 arrowprops=dict(arrowstyle="-", color=INK["muted"], lw=0.8))
    ax1.legend(loc="upper left", ncols=3, bbox_to_anchor=(0, 0.9))

    ma = f["ma13"].where(f["ma13"] > 0.2)
    ax2.plot(ma.index, ma, color=SERIES[0], lw=2.0)
    ax2.set_yscale("log")
    ax2.set_ylim(0.2, 400)
    ax2.set_yticks([0.3, 1, 3, 10, 30, 100], ["0.3", "1", "3", "10", "30", "100"])
    ax2.set_ylabel("13주 이동평균 (로그 눈금)")
    mark_break(ax2, label=False)
    for key, label, (a, b), y in [("2023_2024", "2023~24", ("2023-01-01", "2024-12-29"), 0.45),
                                  ("2025", "2025", ("2025-01-05", "2025-12-28"), 2.0),
                                  ("2026h1", "2026 상반기", ("2026-01-04", PRE_LAST), 200)]:
        weeks, growth = numbers[f"doubling_{key}"], numbers[f"weekly_growth_pct_{key}"]
        mid = pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2
        if weeks is not None and weeks < 200:
            text = f"{label}: 주 {growth:+.1f}% → 약 {weeks:.0f}주마다 2배"
        else:
            text = f"{label}: 주 {growth:+.1f}% → 사실상 정체"
        ax2.text(mid, y, text, ha="center", fontsize=8.5, color=INK["secondary"],
                 bbox=dict(boxstyle="round,pad=0.25", fc=INK["surface"], ec="none"))
    date_axis(ax2)
    finish(fig, ax1, "미국 'AI shopping' 검색 관심도: 2025년부터 가파르게 오르고 2026년 7월에 꺾였다",
           "위: 실제 값(주간)과 이동평균(단절 앞뒤를 따로 계산) · 아래: 같은 13주 이동평균을 로그 눈금으로(같은 기울기 = 같은 증가 속도)\n" + event_key(EVENTS_US),
           "출처: Google Trends — 미국, 주간, 2021-10-24~2026-10-18(진행 중인 마지막 주 제외) · 이동평균은 가운데 정렬",
           "01_trend_moving_average.png")


def fig02_quarterly(f):
    s = f[MAIN]
    q = s["2022-01-01":"2026-09-30"].resample("QE").mean()
    qoq = (q / q.shift(1) - 1).where(q.shift(1) >= 1) * 100   # 직전 분기 평균이 1 미만이면 계산하지 않음
    fig, (ax1, ax2) = new_fig(2, 1, height=7.0, gridspec_kw={"height_ratios": [3, 2]})
    x = np.arange(len(q))
    ax1.bar(x, q.values, width=0.42, color=SERIES[0], zorder=2)
    for i, (v, g) in enumerate(zip(q.values, qoq.values)):
        if q.index[i] >= pd.Timestamp("2024-10-01"):
            label = f"{v:.1f}" + (f"\n({g:+.0f}%)" if g == g and q.values[i - 1] >= 1 else "")
            ax1.text(i, v + 1.2, label, ha="center", va="bottom", fontsize=8, color=INK["secondary"])
    ax1.set_xticks(x, [f"{d.year}\nQ{d.quarter}" if d.quarter == 1 else f"Q{d.quarter}" for d in q.index])
    ax1.set_ylim(0, q.max() * 1.25)
    ax1.set_ylabel("분기 평균 (기간 최댓값=100)")
    ax1.grid(axis="x", visible=False)

    vol = f["vol13"]["2025-01-01":]
    ax2.plot(vol.index, vol, color=SERIES[0], lw=1.8)
    ax2.set_ylabel("주간 변화율의 13주 표준편차 (%)")
    ax2.set_ylim(0, vol.max() * 1.15)
    mark_break(ax2, label=False)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    finish(fig, ax1, "분기 평균으로 보면 2025년 3분기에 계단식으로 올라섰고, 성장 속도는 2026년에 둔화했다",
           "위: 분기 평균과 전분기 대비 증가율(2024 Q4부터 표기) · 아래: 변동성 = 최근 13주 동안 '전주 대비 변화율'의 표준편차(2025년부터, 높을수록 출렁임)",
           "출처: Google Trends — 미국 'AI shopping', 주간 → 분기 평균. 2026 Q3에는 7월 중순 단절이 포함돼 있다.",
           "02_quarterly_volatility.png")
    return q, qoq


def fig03_spikes(f, us):
    s = f[MAIN]["2024-01-01":]
    z = f["spike_z"]["2024-01-01":]
    spikes = s[(z >= 2.5) & (s >= 5)]
    fig, (ax1, ax2) = new_fig(2, 1, height=7.0, sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    ax1.plot(s.index, s, color=SERIES[0], lw=1.6)
    ax1.scatter(spikes.index, spikes.values, s=46, color=SERIES[0], edgecolor=INK["surface"],
                linewidth=2, zorder=3, label="급등 주(직전 8주 중앙값 대비 z ≥ 2.5)")
    ax1.set_ylim(0, 114)
    ax1.set_yticks([0, 20, 40, 60, 80, 100])
    ax1.set_ylabel("검색 관심도")
    mark_break(ax1, y_frac=0.62)
    mark_events(ax1, EVENTS_US, y=113)
    for d in BLACK_FRIDAY[-2:]:
        w = week_of(d)
        ax1.text(w, 2, "BF", ha="center", fontsize=8, color=INK["muted"])
    ax1.legend(loc="upper left", bbox_to_anchor=(0, 0.9))

    w = f["wow_pct"]["2024-01-01":]
    colors = np.where(w >= 0, POS, NEG)
    ax2.bar(w.index, w.values, width=4.2, color=colors, zorder=2)
    ax2.axhline(0, color=INK["axis"], lw=0.8)
    ax2.set_ylabel("전주 대비 변화율 (%)")
    mark_break(ax2, label=False)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    finish(fig, ax1, "급등 주는 AI 쇼핑 기능 발표 직후와 블랙프라이데이(BF) 주에 몰려 있다",
           "위: 주간 값과 급등 주 · 아래: 전주 대비 변화율(직전 주 값이 5 미만이면 계산하지 않음)\n" + event_key(EVENTS_US),
           "출처: Google Trends — 미국 'AI shopping', 주간. 사건 날짜는 각 회사 발표·주요 보도 기준.",
           "03_spikes_events.png")
    return spikes


def fig04_keywords(us):
    cols = list(us.columns)
    ma = rolling_by_segment(us, 4, center=True, min_periods=3)["2023-01-01":]
    fig, (ax1, ax2) = new_fig(2, 1, height=7.4, gridspec_kw={"height_ratios": [3, 2]})
    for i, c in enumerate(cols):
        ax1.plot(ma.index, ma[c], color=SERIES[i], lw=2.2 if c == MAIN else 1.6, label=c)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("4주 이동평균 (같은 요청 안에서 최댓값=100)")
    mark_break(ax1)
    date_axis(ax1)
    ax1.legend(loc="upper left", ncols=5)

    q = us["2024-01-01":"2026-09-30"].resample("QE").mean()
    share = q.div(q.sum(axis=1), axis=0) * 100
    x = np.arange(len(share))
    bottom = np.zeros(len(share))
    for i, c in enumerate(cols):
        ax2.bar(x, share[c].values, bottom=bottom, width=0.5, color=SERIES[i],
                edgecolor=INK["surface"], linewidth=1.5, zorder=2)
        bottom += share[c].values
    ax2.set_xticks(x, [f"{d.year}\nQ{d.quarter}" if d.quarter == 1 else f"Q{d.quarter}" for d in share.index])
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("분기별 비중 (%)")
    ax2.grid(axis="x", visible=False)
    finish(fig, ax1, "관심의 대부분은 일반어 'AI shopping'이고, 'agentic commerce'의 비중이 2025년 말부터 커졌다",
           "위: 다섯 검색어의 4주 이동평균(한 번에 요청해 같은 눈금) · 아래: 분기별 합계에서 각 검색어가 차지한 비중",
           "출처: Google Trends — 미국, 주간. 비중은 검색량의 상대 비교이며 실제 검색 횟수가 아니다.",
           "04_keyword_mix.png")
    return share


def fig05_break(data, table):
    idx_series = [
        ("AI shopping (Google, 미국)", data["trends_us_weekly"][MAIN]),
        ("Agentic commerce 위키백과 조회수", data["wiki_en_agentic_commerce"]),
        ("online shopping (Google, 미국)", data["trends_us_controls_longtail"]["online shopping"]),
        ("ChatGPT (Google, 미국)", data["trends_us_controls_highvol"]["ChatGPT"]),
    ]
    fig, (ax1, ax2) = new_fig(1, 2, height=6.0, gridspec_kw={"width_ratios": [5, 4]})
    for i, (label, s) in enumerate(idx_series):
        x = s["2026-03-01":POST[1]]
        x = x / s[PRE[0]:PRE[1]].mean() * 100
        ax1.plot(x.index, x, color=SERIES[i], lw=2.2 if i == 0 else 1.6, label=label)
    ax1.axhline(100, color=INK["axis"], lw=0.8)
    ax1.set_ylim(0, 260)
    ax1.set_ylabel("급락 전 10주 평균 = 100")
    mark_break(ax1, y_frac=0.72)
    wiki = idx_series[1][1]
    wiki_peak = wiki[POST[0]:POST[1]].idxmax()
    ax1.annotate(f"{wiki_peak:%m-%d} 주 {wiki[wiki_peak] / wiki[PRE[0]:PRE[1]].mean() * 100:.0f}(축 밖)",
                 (wiki_peak, 258), xytext=(6, -4), textcoords="offset points", ha="left", va="top",
                 fontsize=8, color=INK["secondary"])
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m월"))
    ax1.legend(loc="upper left", fontsize=8.5)
    ax1.set_title("같은 기준으로 맞춘 주간 추이(2026-03~10)", loc="left", fontsize=9.5, pad=10)

    groups = ["AI 관련", "위키백과 조회수", "비AI 쇼핑 검색어", "대형 일반 검색어"]
    t = table.copy()
    t["order"] = t["묶음"].map({g: i for i, g in enumerate(groups)})
    t = t.sort_values(["order", "변화율(%)"], ascending=[False, False]).reset_index(drop=True)
    y = np.arange(len(t))
    ax2.barh(y, t["변화율(%)"], height=0.55, color=[SERIES[groups.index(g)] for g in t["묶음"]], zorder=2)
    for yi, v in zip(y, t["변화율(%)"]):
        ax2.text(v + (2 if v >= 0 else -2), yi, f"{v:+.0f}%", va="center", ha="left" if v >= 0 else "right",
                 fontsize=8, color=INK["secondary"])
    ax2.set_yticks(y, t["계열"], fontsize=8.5)
    ax2.axvline(0, color=INK["axis"], lw=0.8)
    ax2.set_xlim(-100, 45)
    ax2.grid(axis="y", visible=False)
    ax2.grid(axis="x", visible=True)
    ax2.set_xlabel("(급락 후 14주 평균 ÷ 급락 전 10주 평균 - 1) × 100 (%)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=SERIES[i]) for i in range(len(groups))]
    ax2.legend(handles, groups, loc="upper right", fontsize=8)
    ax2.set_title("급락 전후 평균 변화율", loc="left", fontsize=9.5, pad=10)
    fig.suptitle("7월 급락은 Google의 AI·쇼핑 소량 검색어에 몰려 있고, 대형 검색어와 위키백과 조회수에는 없다",
                 x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK["primary"])
    fig.supxlabel(f"급락 전 = {PRE[0]}~{PRE[1]} 주 · 급락 후 = {POST[0]}~{POST[1]} 주(전환 주 {BREAK_WEEK} 제외). "
                  "출처: Google Trends(미국·한국 주간), Wikimedia Pageviews(영어 위키백과, 사용자 조회).",
                  x=0.01, ha="left", fontsize=8, color=INK["muted"])
    fig.savefig(IMAGES / "05_break_check.png")
    plt.close(fig)
    print("  그림 저장: images/05_break_check.png")


def fig06_daily(daily, numbers):
    cols = [MAIN, "price comparison", "online shopping"]
    ma7 = daily[cols].rolling(7, center=True, min_periods=4).mean()
    fig, (ax1, ax2) = new_fig(1, 2, height=5.4, gridspec_kw={"width_ratios": [5, 2]})
    for i, c in enumerate(cols):
        ax1.plot(daily.index, daily[c], color=SERIES[i], lw=0.8, alpha=0.3)
        ax1.plot(ma7.index, ma7[c], color=SERIES[i], lw=2.0, label=f"{c} (7일 이동평균)")
    a, b = numbers["daily_drop_start"], numbers["daily_drop_end"]
    ax1.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=INK["wash"], zorder=0, lw=0)
    ax1.text(pd.Timestamp(a), 97, f"하락 구간\n{a[5:]}~{b[5:]}", fontsize=8, color=INK["muted"], va="top")
    ax1.set_xlim(daily.index.min() - pd.Timedelta(days=3), daily.index.max() + pd.Timedelta(days=3))
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("일간 관심도 (같은 요청 안에서 최댓값=100)")
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m월"))
    ax1.legend(loc="upper right", fontsize=8.5)
    ax1.set_title("일간 값(옅은 선)과 7일 이동평균(진한 선)", loc="left", fontsize=9.5, pad=10)

    wk = numbers["weekday_index"]
    days = ["월", "화", "수", "목", "금", "토", "일"]
    x = np.arange(7)
    width = 0.26
    for i, c in enumerate(cols):
        ax2.bar(x + (i - 1) * width, [wk[c][d] - 100 for d in range(7)], width=width * 0.9,
                color=SERIES[i], zorder=2)
    ax2.axhline(0, color=INK["axis"], lw=0.8)
    ax2.set_ylim(-15, 15)
    ax2.set_xticks(x, days)
    ax2.set_ylabel("전체 평균 대비 (%)")
    ax2.grid(axis="x", visible=False)
    ax2.set_title("요일별 지수(급락 전 05-01~07-05)", loc="left", fontsize=9.5, pad=10)
    fig.suptitle("일 단위로 보면 하락은 하루가 아니라 약 열흘에 걸쳐 일어났고, 요일 차이는 ±10% 안팎이다",
                 x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK["primary"])
    fig.supxlabel("하락 구간 = 'AI shopping' 7일 이동평균이 급락 전 평균의 75% 아래로 처음 내려간 날 ~ 40% 아래로 처음 내려간 날. "
                  "출처: Google Trends — 미국, 일간, 2026-05-01~2026-09-30(세 검색어를 한 번에 요청).",
                  x=0.01, ha="left", fontsize=8, color=INK["muted"])
    fig.savefig(IMAGES / "06_daily_weekday.png")
    plt.close(fig)
    print("  그림 저장: images/06_daily_weekday.png")


def fig07_us_kr(us, kr, numbers):
    a = rolling_by_segment(us[MAIN], 4, center=True, min_periods=3)["2024-01-01":]
    b = rolling_by_segment(kr[KR], 4, center=True, min_periods=3)["2024-01-01":]
    fig, ax = new_fig(1, 1, height=5.4)
    ax.plot(a.index, a, color=SERIES[0], lw=2.2, label="미국 'AI shopping'")
    ax.plot(b.index, b, color=SERIES[1], lw=2.2, label="한국 'AI 쇼핑'")
    ax.plot(kr[KR]["2024-01-01":].index, kr[KR]["2024-01-01":], color=SERIES[1], lw=0.8, alpha=0.3)
    ax.set_ylim(0, 105)
    ax.set_ylabel("4주 이동평균 (각자 기간 최댓값=100)")
    mark_break(ax)
    for i, (d, name) in enumerate(EVENTS_KR):
        x = pd.Timestamp(d)
        ax.axvline(x, color=INK["axis"], lw=0.8, zorder=0)
        ax.text(x, 103, f"K{i + 1}", ha="center", va="top", fontsize=9, color=INK["secondary"],
                bbox=dict(boxstyle="round,pad=0.15", fc=INK["surface"], ec="none"))
    for key, s, color, dx in [("takeoff25_us", a, SERIES[0], -10), ("takeoff25_kr", b, SERIES[1], 10)]:
        t = pd.Timestamp(numbers[key])
        ax.scatter([t], [s[t]], s=46, color=color, edgecolor=INK["surface"], linewidth=2, zorder=3)
        ax.annotate(f"25 첫 도달\n{t:%Y-%m-%d} 주", (t, s[t]), xytext=(dx, 0), textcoords="offset points",
                    fontsize=8.5, color=INK["secondary"], ha="right" if dx < 0 else "left", va="center")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="upper left")
    lag = numbers["takeoff25_lag_weeks"]
    finish(fig, ax, f"한국 'AI 쇼핑'은 미국보다 약 {lag}주 늦게 올라섰고, 꺾인 시점은 미국과 같은 주였다",
           "4주 이동평균 · 두 나라 값은 각자 최댓값 기준이라 높이(검색량)가 아니라 모양과 시점만 비교한다\n"
           + "  ".join(f"K{i + 1} {d} {n}" for i, (d, n) in enumerate(EVENTS_KR)),
           "출처: Google Trends — 미국 'AI shopping'·한국 'AI 쇼핑' 각각 단독 요청, 주간. 한국 검색은 네이버 비중이 커 Google 값이 전체 관심을 대표하지 않는다.",
           "07_us_vs_kr.png")


def stl_parts(s: pd.Series):
    # 주기가 3~4번뿐이라 해마다 달라지는 계절성은 추정할 수 없다 → 계절 패턴을 고정(seasonal=999)하고,
    # 추세 창은 허용 최소(53주)로 둬 빠른 성장을 따라가게 한다.
    res = STL(np.log1p(s), period=52, trend=53, seasonal=999, seasonal_deg=0).fit()
    t, se, r = res.trend, res.seasonal, res.resid
    strength_t = max(0.0, 1 - r.var() / (t + r).var())
    strength_s = max(0.0, 1 - r.var() / (se + r).var())
    return res, strength_t, strength_s


def fig08_decompose(us, lt, numbers):
    ai = us[MAIN]["2023-01-01":PRE_LAST]
    on = lt["online shopping"][:PRE_LAST]
    fig, axes = new_fig(4, 2, height=8.6, sharex="col")
    for col, (label, s, color) in enumerate([("AI shopping", ai, SERIES[0]), ("online shopping (대조)", on, SERIES[2])]):
        res, st, ss = stl_parts(s)
        key = "ai" if col == 0 else "online"
        numbers[f"stl_{key}_trend_strength"] = round(st, 2)
        numbers[f"stl_{key}_seasonal_strength"] = round(ss, 2)
        parts = [("관측값 log(1+x)", res.observed), ("추세", res.trend), ("계절성(52주)", res.seasonal), ("나머지(노이즈)", res.resid)]
        for row, (name, v) in enumerate(parts):
            ax = axes[row, col]
            if row == 3:
                ax.bar(v.index, v.values, width=5, color=color, zorder=2)
                ax.axhline(0, color=INK["axis"], lw=0.8)
            else:
                ax.plot(v.index, v.values, color=color, lw=1.8)
            if row == 2:
                ax.axhline(0, color=INK["axis"], lw=0.8)
            ax.set_ylabel(name, fontsize=8.5)
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        month_idx = (np.exp(res.seasonal) - 1).groupby(res.seasonal.index.month).mean() * 100
        numbers[f"stl_{key}_month_effect_pct"] = month_idx.round(1).to_dict()
        total = res.trend.var() + res.seasonal.var() + res.resid.var()
        share = {"trend": res.trend.var() / total * 100, "seasonal": res.seasonal.var() / total * 100,
                 "resid": res.resid.var() / total * 100}
        numbers[f"stl_{key}_variance_share_pct"] = {k: round(v, 1) for k, v in share.items()}
        axes[0, col].set_title(f"{label} — 변동 비중: 추세 {share['trend']:.0f}% · 계절 {share['seasonal']:.0f}% · "
                               f"나머지 {share['resid']:.0f}%\n11월 계절 효과 {month_idx[11]:+.0f}% · 강도(0~1) 추세 {st:.2f} · 계절 {ss:.2f}",
                               loc="left", fontsize=9.5, pad=10, color=INK["secondary"])
    fig.suptitle("'AI shopping' 변동의 대부분은 추세이고, 연말 계절성이 뚜렷한 'online shopping'과 다르다",
                 x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK["primary"])
    fig.supxlabel("STL 분해(주기 52주, 추세 창 53주, 계절 패턴 고정) · 로그 변환 후 분해해 계절성을 '비율' 효과로 본다 · 강도는 0~1(1에 가까울수록 해당 성분이 뚜렷).\n"
                  f"구간: AI shopping 2023-01~{PRE_LAST[:7]}, online shopping 2021-10~{PRE_LAST[:7]}(단절 이후 제외).",
                  x=0.01, ha="left", fontsize=8, color=INK["muted"])
    fig.savefig(IMAGES / "08_stl_decomposition.png")
    plt.close(fig)
    print("  그림 저장: images/08_stl_decomposition.png")


def baseline_forecasts(train: pd.Series, horizon_index):
    h = np.arange(1, len(horizon_index) + 1)
    last = train.iloc[-1]
    tail = train.iloc[-26:]
    slope = (tail.iloc[-1] - tail.iloc[0]) / (len(tail) - 1)
    snaive = [train.get(d - pd.Timedelta(weeks=52), np.nan) for d in horizon_index]
    return pd.DataFrame({
        "naive(마지막 값)": last,
        "4주 평균": train.iloc[-4:].mean(),
        "drift(최근 26주 기울기)": last + slope * h,
        "계절 naive(52주 전 값)": snaive,
    }, index=horizon_index)


def fig09_forecast(s: pd.Series, numbers):
    # (1) 정상 구간 검증: 2026-03-29 까지로 학습, 다음 14주(단절 전)를 맞혀 본다
    train = s[:"2026-03-29"]
    test = s["2026-04-05":PRE_LAST]
    fc = baseline_forecasts(train, test.index)
    err = pd.DataFrame({
        "MAE": (fc.sub(test, axis=0)).abs().mean(),
        "MAPE(%)": (fc.sub(test, axis=0)).abs().div(test, axis=0).mean() * 100,
    }).round(1)
    # (2) 단절 시나리오: 2026-07-05 까지로 학습, 다음 15주를 맞혀 본다
    train2 = s[:PRE_LAST]
    test2 = s[BREAK_WEEK:POST[1]]
    fc2 = baseline_forecasts(train2, test2.index)
    err2 = pd.DataFrame({"MAE": (fc2.sub(test2, axis=0)).abs().mean(),
                         "MAPE(%)": (fc2.sub(test2, axis=0)).abs().div(test2, axis=0).mean() * 100}).round(1)
    # (3) 앞으로 10주: 마지막 완결 주까지로 학습. 무작위 보행 가정의 80% 구간을 함께 낸다
    future = pd.date_range(pd.Timestamp(POST[1]) + pd.Timedelta(weeks=1), periods=10, freq="7D")
    post = s[POST[0]:POST[1]]
    sigma = post.diff().std()
    fwd = pd.DataFrame({"naive": post.iloc[-1], "4주 평균": post.iloc[-4:].mean()}, index=future)
    band = 1.2816 * sigma * np.sqrt(np.arange(1, len(future) + 1))
    numbers["forecast_forward_level"] = round(float(post.iloc[-4:].mean()), 1)
    numbers["forecast_forward_sigma"] = round(float(sigma), 2)

    fig, (ax1, ax2) = new_fig(1, 2, height=5.6, gridspec_kw={"width_ratios": [1, 1]}, sharey=True)
    for ax, tr, te, f in [(ax1, train, test, fc), (ax2, train2, test2, fc2)]:
        ctx = tr["2025-10-01":]
        ax.plot(ctx.index, ctx, color=INK["primary"], lw=1.6, label="실제(학습 구간)")
        ax.plot(te.index, te, color=INK["primary"], lw=2.4, label="실제(평가 구간)")
        for i, c in enumerate(f.columns):
            ax.plot(f.index, f[c], color=SERIES[i], lw=1.8, linestyle=(0, (4, 2)), label=c)
        ax.axvline(te.index[0] - pd.Timedelta(days=3.5), color=INK["axis"], lw=0.8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.plot(fwd.index, fwd["4주 평균"], color=SERIES[1], lw=1.8, linestyle=(0, (1, 2)))
    ax2.fill_between(fwd.index, (fwd["4주 평균"] - band).clip(lower=0), fwd["4주 평균"] + band,
                     color=SERIES[1], alpha=0.10, lw=0)
    ax2.text(fwd.index[-1], fwd["4주 평균"].iloc[-1] + band[-1] + 18, "앞으로 10주\n(4주 평균 ±80% 구간)",
             fontsize=8, color=INK["secondary"], ha="right")
    ax1.set_ylim(0, 140)
    ax1.set_ylabel("검색 관심도")
    best = err["MAE"].idxmin()
    ax1.set_title(f"① 정상 구간 검증: ~2026-03-29 학습 → 14주 예측\n가장 나은 방법 = {best}, MAE {err.loc[best, 'MAE']:.1f}",
                  loc="left", fontsize=9.5, pad=10)
    trend_like = err2.drop(index="계절 naive(52주 전 값)")["MAE"]
    ax2.set_title(f"② 단절 구간: ~{PRE_LAST} 학습 → 15주 예측\n최근 흐름 기반 3종 MAE {trend_like.min():.0f}~{trend_like.max():.0f} · "
                  f"계절 naive {err2.loc['계절 naive(52주 전 값)', 'MAE']:.1f}(작년 수준과 우연히 비슷)",
                  loc="left", fontsize=9.5, pad=10)
    ax1.legend(loc="upper left", fontsize=8)
    fig.suptitle("단순 예측은 흐름이 유지되는 동안엔 쓸 만했지만, 7월 같은 단절은 어떤 방법도 예측하지 못했다",
                 x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK["primary"])
    fig.supxlabel("점선 = 예측. MAE = 평균 절대 오차(관심도 포인트). 예측 구간은 최근 14주 주간 변화의 표준편차로 만든 무작위 보행 근사이며, 연말 쇼핑 시즌 효과는 넣지 않았다.",
                  x=0.01, ha="left", fontsize=8, color=INK["muted"])
    fig.savefig(IMAGES / "09_baseline_forecast.png")
    plt.close(fig)
    print("  그림 저장: images/09_baseline_forecast.png")
    return err, err2, fwd.assign(lower80=(fwd["4주 평균"] - band).clip(lower=0), upper80=fwd["4주 평균"] + band)


# ---------------------------------------------------------------- 실행

def main() -> None:
    for d in (PROCESSED, IMAGES, OUTPUTS):
        d.mkdir(parents=True, exist_ok=True)
    setup_style()
    data = load_all()
    us, lt, kr, daily = (data["trends_us_weekly"], data["trends_us_controls_longtail"],
                         data["trends_kr_weekly"], data["daily"])
    f = build_features(us)
    f.round(3).to_csv(PROCESSED / "us_weekly_clean.csv")
    s = us[MAIN]
    numbers = {"weeks": len(s), "start": str(s.index.min().date()), "end": str(s.index.max().date()),
               "peak_week": str(s.idxmax().date()), "first_nonzero_week": str(s[s > 0].index[0].date()),
               "zero_weeks_main": int((s == 0).sum()), "zero_weeks_kr": int((kr[KR] == 0).sum())}

    # 연·분기·구간 통계
    yearly = s[:PRE_LAST].groupby(s[:PRE_LAST].index.year).mean().round(2)
    numbers["yearly_mean"] = yearly.to_dict()
    numbers["mean_2026_pre_break"] = round(s["2026-01-04":PRE_LAST].mean(), 1)
    numbers["mean_post_break"] = round(s[POST[0]:POST[1]].mean(), 1)
    numbers["vol13_mean_2025h2"] = round(float(f["vol13"]["2025-07-06":"2025-12-28"].mean()), 1)
    numbers["vol13_mean_2026h1"] = round(float(f["vol13"]["2026-01-04":PRE_LAST].mean()), 1)
    phases = phase_table(s)
    phases.to_csv(OUTPUTS / "phase_stats.csv", index=False)
    for key, (a, b) in {"doubling_2023_2024": ("2023-01-01", "2024-12-29"),
                        "doubling_2025": ("2025-01-05", "2025-12-28"),
                        "doubling_2026h1": ("2026-01-04", PRE_LAST)}.items():
        weeks, slope = doubling_weeks(f["ma13"], a, b)
        numbers[key] = round(float(weeks), 1) if weeks == weeks else None
        numbers[key.replace("doubling", "weekly_growth_pct")] = round(float((np.exp(slope) - 1) * 100), 2)

    events = event_table(s, EVENTS_US)
    events.to_csv(OUTPUTS / "event_windows.csv", index=False)
    events_kr = event_table(kr[KR], EVENTS_KR)
    events_kr.to_csv(OUTPUTS / "event_windows_kr.csv", index=False)
    bf = black_friday_table({"AI shopping": s, "online shopping": lt["online shopping"]})
    bf.to_csv(OUTPUTS / "black_friday.csv", index=False)

    for name, series, key in [("us", s, "us"), ("kr", kr[KR], "kr")]:
        for level in (10, 25):
            t = takeoff(series[:PRE_LAST], level)
            numbers[f"takeoff{level}_{key}"] = str(t.date()) if t is not None else None
    for level in (10, 25):
        numbers[f"takeoff{level}_lag_weeks"] = int(
            (pd.Timestamp(numbers[f"takeoff{level}_kr"]) - pd.Timestamp(numbers[f"takeoff{level}_us"])).days // 7)

    brk = break_table(data)
    brk.to_csv(OUTPUTS / "break_check.csv", index=False)

    # 일간: 7일 이동평균이 급락 전 평균의 75% 아래로 처음 내려간 날 ~ 40% 아래로 처음 내려간 날
    m7 = daily[MAIN].rolling(7, center=True, min_periods=4).mean()
    pre_mean = daily[MAIN]["2026-05-01":PRE_LAST].mean()
    after = m7["2026-07-01":]
    numbers["daily_drop_start"] = str(after[after < pre_mean * 0.75].index[0].date())
    numbers["daily_drop_end"] = str(after[after < pre_mean * 0.40].index[0].date())
    pre_daily = daily["2026-05-01":PRE_LAST]
    wk = pre_daily.groupby(pre_daily.index.day_of_week).mean() / pre_daily.mean() * 100
    numbers["weekday_index"] = {c: {int(k): round(v, 1) for k, v in wk[c].items()} for c in wk.columns}

    print("그림 생성")
    fig01_trend(f, numbers)
    q, qoq = fig02_quarterly(f)
    pd.DataFrame({"분기 평균": q.round(2), "전분기 대비(%)": qoq.round(1)}).to_csv(OUTPUTS / "quarterly.csv")
    spikes = fig03_spikes(f, us)
    pd.DataFrame({"값": spikes, "z": f["spike_z"].reindex(spikes.index).round(2),
                  "전주 대비(%)": f["wow_pct"].reindex(spikes.index).round(1)}).to_csv(OUTPUTS / "spikes.csv")
    share = fig04_keywords(us)
    share.round(1).to_csv(OUTPUTS / "keyword_share_quarterly.csv")
    fig05_break(data, brk)
    fig06_daily(daily, numbers)
    fig07_us_kr(us, kr, numbers)
    fig08_decompose(us, lt, numbers)
    err, err2, fwd = fig09_forecast(s, numbers)
    err.to_csv(OUTPUTS / "forecast_holdout_errors.csv")
    err2.to_csv(OUTPUTS / "forecast_break_errors.csv")
    fwd.round(1).to_csv(OUTPUTS / "forecast_forward.csv")

    (OUTPUTS / "key_numbers.json").write_text(json.dumps(numbers, ensure_ascii=False, indent=2, default=str),
                                              encoding="utf-8")
    print("\n주요 수치")
    print(json.dumps(numbers, ensure_ascii=False, indent=1, default=str))
    for title, table in [("구간 통계", phases), ("사건 전후(미국)", events), ("사건 전후(한국)", events_kr),
                         ("블랙프라이데이 주 배수", bf), ("급락 전후", brk), ("급등 주", spikes),
                         ("예측 검증(정상)", err), ("예측 검증(단절)", err2)]:
        print(f"\n[{title}]")
        print(table.to_string())


if __name__ == "__main__":
    main()
