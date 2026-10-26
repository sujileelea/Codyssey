"""대시보드 생성 — data/raw/ 의 CSV 를 한 개의 HTML(dashboard/index.html)에 담는다.

실행: python build_dashboard.py   → dashboard/index.html 을 브라우저로 열면 된다(서버·인터넷 불필요).
화면 상태(묶음·보기·집계·이동평균·기간·숨긴 계열)는 주소의 ? 뒤에 저장돼 그대로 공유·재현된다.
"""

import json
from pathlib import Path

import pandas as pd

from analysis import BLACK_FRIDAY, EVENTS_KR, EVENTS_US, POST, PRE_LAST, load_trends, load_wiki_weekly

BASE = Path(__file__).resolve().parent
OUT = BASE / "dashboard" / "index.html"

GROUPS = [
    {"id": "us", "label": "미국 AI 쇼핑 검색어 5종", "file": "trends_us_weekly",
     "note": "한 번에 요청한 다섯 검색어라 높이를 서로 비교할 수 있다(이 묶음 안 최댓값 = 100).",
     "series": [("AI shopping", "AI shopping"), ("AI shopping assistant", "AI shopping assistant"),
                ("ChatGPT shopping", "ChatGPT shopping"), ("agentic commerce", "agentic commerce"),
                ("Amazon Rufus", "Amazon Rufus")]},
    {"id": "uskr", "label": "미국 vs 한국", "file": None,
     "note": "두 나라 값은 각자 최댓값 = 100 이라 높이가 아니라 모양과 시점을 비교한다.",
     "series": [("us:AI shopping", "미국 'AI shopping'"), ("kr:AI 쇼핑", "한국 'AI 쇼핑'")]},
    {"id": "longtail", "label": "대조: 쇼핑 소량 검색어(미국)", "file": "trends_us_controls_longtail",
     "note": "'AI shopping' 과 비슷한 규모의 비(非)AI 쇼핑 검색어. 7월 급락 검증용(같은 요청 안 최댓값 = 100).",
     "series": [("AI shopping", "AI shopping"), ("online shopping", "online shopping"),
                ("price comparison", "price comparison"), ("shopping list", "shopping list")]},
    {"id": "highvol", "label": "대조: 대형 일반 검색어(미국)", "file": "trends_us_controls_highvol",
     "note": "검색량이 큰 일반 검색어. 전체 검색량이 바뀌었는지 확인하는 기준선(같은 요청 안 최댓값 = 100).",
     "series": [("ChatGPT", "ChatGPT"), ("Amazon", "Amazon"), ("weather", "weather")]},
    {"id": "wiki", "label": "교차 확인: 영어 위키백과 조회수", "file": None,
     "note": "Google 과 독립된 측정. 단위는 주간 조회수(회)라 다른 묶음과 높이를 비교하지 않는다.",
     "series": [("wiki:Agentic_commerce", "Agentic commerce 문서"), ("wiki:Online_shopping", "Online shopping 문서")]},
]


def build_payload() -> dict:
    us, _ = load_trends("trends_us_weekly")
    dates = us.index
    frames = {g["file"]: load_trends(g["file"])[0] for g in GROUPS if g["file"]}
    kr, _ = load_trends("trends_kr_weekly")
    wiki = {"Agentic_commerce": load_wiki_weekly("wiki_en_agentic_commerce")[0],
            "Online_shopping": load_wiki_weekly("wiki_en_online_shopping")[0]}

    def values(s: pd.Series):
        s = s.reindex(dates)
        return [None if pd.isna(v) else float(v) for v in s]

    groups = []
    for g in GROUPS:
        series = []
        for key, label in g["series"]:
            if key.startswith("us:"):
                s = us[key[3:]]
            elif key.startswith("kr:"):
                s = kr[key[3:]]
            elif key.startswith("wiki:"):
                s = wiki[key[5:]]
            else:
                s = frames[g["file"]][key]
            series.append({"key": key, "label": label, "values": values(s)})
        groups.append({"id": g["id"], "label": g["label"], "note": g["note"], "series": series,
                       "unit": "주간 조회수" if g["id"] == "wiki" else "검색 관심도"})
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "groups": groups,
        "events": {"us": EVENTS_US, "kr": EVENTS_KR, "bf": BLACK_FRIDAY},
        "breakSpan": [PRE_LAST, POST[0]],
        "source": f"Google Trends(주간, {dates.min():%Y-%m-%d}~{dates.max():%Y-%m-%d}) · Wikimedia Pageviews",
    }


TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 쇼핑 관심도 대시보드</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --wash: #f0efec; --border: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4;
  --focus: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --wash: #262624; --border: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --focus: #3987e5;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --wash: #262624; --border: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --focus: #3987e5;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font-family: system-ui, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
  font-size: 14px; line-height: 1.5; }
main { max-width: 1120px; margin: 0 auto; padding: 24px 16px 40px; }
h1 { font-size: 22px; margin: 0 0 4px; font-weight: 700; }
.lead { color: var(--ink-2); margin: 0 0 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.filters { display: flex; flex-wrap: wrap; gap: 12px 16px; align-items: flex-end; margin-bottom: 12px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field > span { font-size: 12px; color: var(--ink-2); }
select, input[type=date], button { font: inherit; color: var(--ink); background: var(--surface);
  border: 1px solid var(--axis); border-radius: 8px; padding: 6px 8px; min-height: 34px; }
button { cursor: pointer; }
button:hover { background: var(--wash); }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.presets { display: flex; gap: 6px; flex-wrap: wrap; }
.presets button { font-size: 13px; padding: 4px 10px; min-height: 30px; }
.toggles { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 4px 0 12px; }
.toggles label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; color: var(--ink-2); }
.swatch { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.note { color: var(--ink-2); font-size: 13px; margin: 0 0 8px; }
.warn { color: var(--ink-2); font-size: 13px; margin: 4px 0 0; }
.chart-wrap { position: relative; }
svg { display: block; width: 100%; height: auto; }
svg text { fill: var(--ink-2); font-size: 11px; }
.tooltip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  min-width: 160px; display: none; }
.tooltip .row { display: flex; align-items: center; gap: 6px; justify-content: space-between; }
.tooltip .row span:first-child { display: inline-flex; align-items: center; gap: 6px; color: var(--ink-2); }
.tooltip b { font-variant-numeric: tabular-nums; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 8px 0 0; color: var(--ink-2); font-size: 13px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.eventkey { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--ink-2); font-weight: 600; }
.summary { margin-top: 16px; overflow-x: auto; }
details { margin-top: 12px; }
details summary { cursor: pointer; color: var(--ink-2); }
.table-scroll { max-height: 360px; overflow: auto; margin-top: 8px; }
footer { color: var(--muted); font-size: 12px; margin-top: 16px; }
</style>
</head>
<body>
<main>
  <h1>AI 쇼핑 관심도 대시보드</h1>
  <p class="lead">Google Trends 검색 관심도로 본 'AI 쇼핑' 관심의 흐름. 묶음·기간·보기·집계 단위를 바꿔 가며 탐색한다.</p>
  <section class="card">
    <div class="filters" role="group" aria-label="필터">
      <label class="field"><span>묶음</span><select id="group"></select></label>
      <label class="field"><span>보기</span>
        <select id="view">
          <option value="raw">원값</option>
          <option value="index">지수(기간 첫 4개 평균 = 100)</option>
          <option value="pop">직전 대비 변화율(%)</option>
          <option value="yoy">전년 같은 시기 대비(%)</option>
        </select></label>
      <label class="field"><span>집계 단위</span>
        <select id="agg"><option value="W">주</option><option value="M">월 평균</option><option value="Q">분기 평균</option></select></label>
      <label class="field"><span>이동평균(집계 단위 기준)</span>
        <select id="ma"><option value="1">없음</option><option value="3">3</option><option value="4">4</option><option value="8">8</option><option value="13">13</option></select></label>
      <label class="field"><span>시작</span><input type="date" id="from"></label>
      <label class="field"><span>끝</span><input type="date" id="to"></label>
      <div class="field"><span>빠른 기간</span>
        <div class="presets">
          <button type="button" data-preset="all">전체</button>
          <button type="button" data-preset="2025">2025~</button>
          <button type="button" data-preset="52">최근 52주</button>
          <button type="button" data-preset="break">급락 전후</button>
        </div></div>
    </div>
    <div class="toggles" id="seriesToggles" role="group" aria-label="계열 표시"></div>
    <div class="toggles">
      <label><input type="checkbox" id="ev"> 사건 표시</label>
      <label><input type="checkbox" id="br"> 단절 의심 구간(2026-07-12 주) 표시</label>
    </div>
    <p class="note" id="groupNote"></p>
    <div class="chart-wrap" id="chartWrap">
      <svg id="chart" role="img" aria-labelledby="chartTitle" tabindex="0"><title id="chartTitle">AI 쇼핑 관심도 추이</title></svg>
      <div class="tooltip" id="tooltip" role="status" aria-live="polite"></div>
    </div>
    <div class="legend" id="legend"></div>
    <p class="warn" id="warn"></p>
    <p class="eventkey" id="eventKey"></p>
    <div class="summary"><table id="summary"></table></div>
    <details><summary>표로 보기(그래프에 그린 값 전체)</summary><div class="table-scroll"><table id="dataTable"></table></div></details>
  </section>
  <footer id="footer"></footer>
</main>
<script>
const DATA = __DATA__;
const COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5"];
const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩";
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const state = { g: "us", view: "raw", agg: "W", ma: 4, from: DATA.dates[0], to: DATA.dates[DATA.dates.length - 1],
  ev: true, br: true, hide: new Set() };

function readURL() {
  try {
    const p = new URLSearchParams(location.search);
    if (p.get("g") && DATA.groups.some((g) => g.id === p.get("g"))) state.g = p.get("g");
    if (["raw", "index", "pop", "yoy"].includes(p.get("view"))) state.view = p.get("view");
    if (["W", "M", "Q"].includes(p.get("agg"))) state.agg = p.get("agg");
    if (p.get("ma") && ["1", "3", "4", "8", "13"].includes(p.get("ma"))) state.ma = +p.get("ma");
    if (/^\d{4}-\d{2}-\d{2}$/.test(p.get("from") || "")) state.from = p.get("from");
    if (/^\d{4}-\d{2}-\d{2}$/.test(p.get("to") || "")) state.to = p.get("to");
    if (p.get("ev") === "0") state.ev = false;
    if (p.get("br") === "0") state.br = false;
    if (p.get("hide")) p.get("hide").split("|").forEach((k) => state.hide.add(k));
  } catch (e) { /* 주소를 읽을 수 없으면 기본값 */ }
}
function writeURL() {
  try {
    const p = new URLSearchParams({ g: state.g, view: state.view, agg: state.agg, ma: state.ma,
      from: state.from, to: state.to, ev: state.ev ? 1 : 0, br: state.br ? 1 : 0 });
    if (state.hide.size) p.set("hide", [...state.hide].join("|"));
    history.replaceState(null, "", "?" + p.toString());
  } catch (e) { /* file:// 등에서 막히면 무시 */ }
}

// 날짜 ↔ 시간값
const toT = (s) => Date.parse(s + "T00:00:00Z");
const fmtDate = (t) => new Date(t).toISOString().slice(0, 10);
function periodKey(s, agg) {
  if (agg === "W") return s;
  const y = s.slice(0, 4), m = +s.slice(5, 7);
  if (agg === "M") return `${y}-${String(m).padStart(2, "0")}-01`;
  return `${y}-${String((Math.ceil(m / 3) - 1) * 3 + 1).padStart(2, "0")}-01`;
}
function aggregate(dates, values, agg) {
  if (agg === "W") return { dates, values };
  const keys = [], sums = new Map(), counts = new Map(), totals = new Map();
  dates.forEach((d, i) => {
    const k = periodKey(d, agg);
    if (!totals.has(k)) { keys.push(k); totals.set(k, 0); sums.set(k, 0); counts.set(k, 0); }
    totals.set(k, totals.get(k) + 1);
    if (values[i] !== null) { sums.set(k, sums.get(k) + values[i]); counts.set(k, counts.get(k) + 1); }
  });
  // 주가 절반도 안 찬 달·분기는 평균을 내지 않는다(양 끝의 덜 찬 기간)
  const need = agg === "M" ? 3 : 7;
  return { dates: keys, values: keys.map((k) => (counts.get(k) >= need ? sums.get(k) / counts.get(k) : null)) };
}
function movingAverage(values, w) {
  if (w <= 1) return values.slice();
  return values.map((_, i) => {
    if (i < w - 1) return null;
    const win = values.slice(i - w + 1, i + 1);
    return win.some((v) => v === null) ? null : win.reduce((a, b) => a + b, 0) / w;
  });
}
function transform(values, view, agg) {
  if (view === "pop") return values.map((v, i) => (i && v !== null && values[i - 1] !== null && values[i - 1] >= 5 ? (v / values[i - 1] - 1) * 100 : null));
  if (view === "yoy") {
    const lag = { W: 52, M: 12, Q: 4 }[agg];
    return values.map((v, i) => (i >= lag && v !== null && values[i - lag] !== null && values[i - lag] >= 1 ? (v / values[i - lag] - 1) * 100 : null));
  }
  return values.slice();
}
function prepare() {
  const group = DATA.groups.find((g) => g.id === state.g);
  const fromT = toT(state.from), toTt = toT(state.to);
  const out = [];
  let warn = "";
  group.series.forEach((s, idx) => {
    const a = aggregate(DATA.dates, s.values, state.agg);
    let v = transform(movingAverage(a.values, state.ma), state.view, state.agg);
    const keep = a.dates.map((d) => toT(d) >= fromT && toT(d) <= toTt);
    let dates = a.dates.filter((_, i) => keep[i]);
    v = v.filter((_, i) => keep[i]);
    if (state.view === "index") {
      // 한 점의 출렁임에 기준이 흔들리지 않게 기간 첫 4개 값의 평균을 100 으로 둔다
      const head = v.filter((x) => x !== null).slice(0, 4);
      const base = head.length ? head.reduce((p, q) => p + q, 0) / head.length : 0;
      if (base < 1) { v = v.map(() => null); warn = "기간 첫 4개 값의 평균이 1 미만인 계열은 지수를 계산하지 않았다."; }
      else v = v.map((x) => (x === null ? null : (x / base) * 100));
    }
    out.push({ key: s.key, label: s.label, color: COLORS[idx], dates, values: v, hidden: state.hide.has(s.key) });
  });
  if (state.view === "pop") warn = "직전 값이 5 미만이면 변화율을 계산하지 않는다(Google Trends 의 0~4 는 반올림 오차가 커서).";
  if (state.view === "yoy") warn = "1년 전 값이 1 미만이면 계산하지 않는다.";
  return { group, series: out, warn };
}

// 눈금
function niceTicks(min, max, n = 5) {
  if (min === max) { max = min + 1; }
  const span = max - min, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(+t.toFixed(10));
  return ticks;
}
const fmtNum = (v) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 10000) return (v / 1000).toFixed(0) + "K";
  if (a >= 1000) return (v / 1000).toFixed(1) + "K";
  return a >= 100 ? v.toFixed(0) : v.toFixed(1);
};
const fmtPct = (v) => (v >= 0 ? "+" : "") + (Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-US") : v.toFixed(1)) + "%";
const fmtVal = (v) => (v === null ? "–" : state.view === "pop" || state.view === "yoy" ? fmtPct(v) : fmtNum(v));

function dateTicks(t0, t1) {
  const years = (t1 - t0) / (365.25 * 864e5), ticks = [];
  const start = new Date(t0), y0 = start.getUTCFullYear();
  const months = years > 3 ? [0] : years > 1.2 ? [0, 3, 6, 9] : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  for (let y = y0; y <= new Date(t1).getUTCFullYear(); y++) {
    months.forEach((m) => { const t = Date.UTC(y, m, 1); if (t >= t0 && t <= t1) ticks.push(t); });
  }
  const label = (t) => (years > 3 ? String(new Date(t).getUTCFullYear()) : fmtDate(t).slice(0, 7));
  return ticks.map((t) => ({ t, label: label(t) }));
}

let geom = null;
function render() {
  const { group, series, warn } = prepare();
  const visible = series.filter((s) => !s.hidden);
  const wrap = $("chartWrap");
  const W = Math.max(320, wrap.clientWidth), narrow = W < 560;
  const H = narrow ? 300 : 420;
  const m = { l: 48, r: narrow ? 12 : 16, t: state.ev ? 34 : 12, b: 28 };
  const svg = $("chart");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const allDates = series[0].dates;
  if (!allDates.length) { svg.innerHTML = ""; return; }
  const t0 = toT(allDates[0]), t1 = toT(allDates[allDates.length - 1]) || t0 + 1;
  const vals = visible.flatMap((s) => s.values.filter((v) => v !== null));
  let lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
  if (state.view === "raw" || state.view === "index") lo = Math.min(0, lo);
  const yt = niceTicks(lo, hi);
  const y0 = yt[0], y1 = yt[yt.length - 1];
  const x = (t) => m.l + ((t - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r);
  const y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  let g = "";
  // 단절 구간
  if (state.br) {
    const a = Math.max(t0, toT(DATA.breakSpan[0])), b = Math.min(t1, toT(DATA.breakSpan[1]));
    if (b > a) g += `<rect x="${x(a)}" y="${m.t}" width="${Math.max(2, x(b) - x(a))}" height="${H - m.t - m.b}" fill="var(--wash)"/>`;
  }
  // 격자·눈금
  yt.forEach((v) => {
    g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 0 ? "var(--axis)" : "var(--grid)"}" stroke-width="1"/>`;
    g += `<text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end" style="font-variant-numeric: tabular-nums">${Number.isInteger(v) ? v.toLocaleString("en-US") : fmtNum(v)}${state.view === "pop" || state.view === "yoy" ? "%" : ""}</text>`;
  });
  let dts = dateTicks(t0, t1);
  const maxTicks = Math.max(2, Math.floor((W - m.l - m.r) / 64));   // 라벨이 겹치지 않을 만큼만
  if (dts.length > maxTicks) { const k = Math.ceil(dts.length / maxTicks); dts = dts.filter((_, i) => i % k === 0); }
  dts.forEach(({ t, label }) => {
    g += `<line x1="${x(t)}" x2="${x(t)}" y1="${H - m.b}" y2="${H - m.b + 4}" stroke="var(--axis)"/>`;
    g += `<text x="${x(t)}" y="${H - m.b + 17}" text-anchor="middle">${label}</text>`;
  });
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--axis)"/>`;
  // 사건
  const evs = state.ev ? (state.g === "uskr" ? DATA.events.kr.map((e, i) => [e[0], "K" + (i + 1), e[1]])
                                             : DATA.events.us.map((e, i) => [e[0], CIRCLED[i], e[1]])) : [];
  let lastX = -99, level = 0;
  evs.forEach(([d, mark]) => {
    const t = toT(d);
    if (t < t0 || t > t1) return;
    const px = x(t);
    level = px - lastX < 18 ? (level + 1) % 2 : 0;
    lastX = px;
    g += `<line x1="${px}" x2="${px}" y1="${m.t}" y2="${H - m.b}" stroke="var(--axis)" stroke-width="1"/>`;
    g += `<text x="${px}" y="${m.t - 8 - level * 12}" text-anchor="middle" style="font-size:12px">${mark}</text>`;
  });
  // 선
  visible.forEach((s) => {
    let d = "", pen = false;
    s.values.forEach((v, i) => {
      if (v === null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(toT(s.dates[i])).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    g += `<path d="${d}" fill="none" stroke="var(${s.color})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  });
  g += `<g id="hover"></g><rect id="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>`;
  svg.innerHTML = `<title id="chartTitle">${group.label} — ${group.unit}</title>` + g;
  geom = { x, y, m, W, H, visible, dates: allDates, idx: null };

  // 범례·주석
  $("legend").innerHTML = visible.map((s) => `<span><i class="swatch" style="background:var(${s.color})"></i>${s.label}</span>`).join("");
  $("groupNote").textContent = group.note + (state.ma > 1 ? ` 이동평균은 직전 ${state.ma}개 ${{ W: "주", M: "달", Q: "분기" }[state.agg]} 평균(후행).` : "");
  $("warn").textContent = warn;
  const shown = evs.filter(([d]) => toT(d) >= t0 && toT(d) <= t1);
  $("eventKey").textContent = shown.length ? "사건: " + shown.map(([d, mk, name]) => `${mk} ${d} ${name}`).join(" · ") : "";
  renderSummary(visible);
  renderTable(visible);
  bindHover();
}

function renderSummary(visible) {
  const rows = visible.map((s) => {
    const pts = s.values.map((v, i) => [s.dates[i], v]).filter((p) => p[1] !== null);
    if (!pts.length) return `<tr><td>${s.label}</td><td colspan="5">값 없음</td></tr>`;
    const vs = pts.map((p) => p[1]);
    const mean = vs.reduce((a, b) => a + b, 0) / vs.length;
    const sd = Math.sqrt(vs.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, vs.length - 1));
    const max = pts.reduce((a, b) => (b[1] > a[1] ? b : a));
    const first = pts[0][1], last = pts[pts.length - 1][1];
    const change = state.view === "raw" || state.view === "index" ? (first >= 1 ? ((last / first - 1) * 100) : null) : null;
    return `<tr><td><i class="swatch" style="background:var(${s.color})"></i> ${s.label}</td><td>${fmtVal(mean)}</td>
      <td>${fmtVal(max[1])} <span style="color:var(--muted)">(${max[0]})</span></td><td>${fmtVal(sd).replace("+", "")}</td>
      <td>${fmtVal(first)} → ${fmtVal(last)}</td><td>${change === null ? "–" : (change >= 0 ? "+" : "") + change.toFixed(0) + "%"}</td></tr>`;
  });
  $("summary").innerHTML = `<thead><tr><th>계열(선택 기간)</th><th>평균</th><th>최대(시점)</th><th>표준편차</th><th>처음 → 끝</th><th>처음 대비 끝</th></tr></thead><tbody>${rows.join("")}</tbody>`;
}
function renderTable(visible) {
  if (!visible.length) { $("dataTable").innerHTML = ""; return; }
  const head = `<thead><tr><th>기간 시작일</th>${visible.map((s) => `<th>${s.label}</th>`).join("")}</tr></thead>`;
  const body = visible[0].dates.map((d, i) => `<tr><td>${d}</td>${visible.map((s) => `<td>${fmtVal(s.values[i])}</td>`).join("")}</tr>`).join("");
  $("dataTable").innerHTML = head + `<tbody>${body}</tbody>`;
}

function showAt(i) {
  if (!geom || i === null) return;
  const { x, y, m, H, visible, dates } = geom;
  i = Math.max(0, Math.min(dates.length - 1, i));
  geom.idx = i;
  const t = toT(dates[i]), px = x(t);
  let h = `<line x1="${px}" x2="${px}" y1="${m.t}" y2="${H - m.b}" stroke="var(--muted)" stroke-width="1"/>`;
  visible.forEach((s) => {
    const v = s.values[i];
    if (v !== null) h += `<circle cx="${px}" cy="${y(v)}" r="4" fill="var(${s.color})" stroke="var(--surface)" stroke-width="2"/>`;
  });
  $("hover").innerHTML = h;
  const tip = $("tooltip");
  const label = state.agg === "W" ? `${dates[i]} 주` : state.agg === "M" ? dates[i].slice(0, 7) : `${dates[i].slice(0, 4)} Q${Math.ceil(+dates[i].slice(5, 7) / 3)}`;
  tip.innerHTML = `<div style="margin-bottom:4px;color:var(--ink)"><b>${label}</b></div>` + visible.map((s) =>
    `<div class="row"><span><i class="swatch" style="background:var(${s.color})"></i>${s.label}</span><b>${fmtVal(s.values[i])}</b></div>`).join("");
  tip.style.display = "block";
  const wrapW = $("chartWrap").clientWidth, scale = wrapW / geom.W;
  const left = px * scale + 12 + tip.offsetWidth > wrapW ? px * scale - tip.offsetWidth - 12 : px * scale + 12;
  tip.style.left = Math.max(0, left) + "px";
  tip.style.top = m.t * scale + "px";
}
function hideTip() { $("tooltip").style.display = "none"; if ($("hover")) $("hover").innerHTML = ""; }
function bindHover() {
  const hit = $("hit"), svg = $("chart");
  const nearest = (evt) => {
    const r = svg.getBoundingClientRect(), px = ((evt.clientX - r.left) / r.width) * geom.W;
    let best = 0, bd = Infinity;
    geom.dates.forEach((d, i) => { const dd = Math.abs(geom.x(toT(d)) - px); if (dd < bd) { bd = dd; best = i; } });
    return best;
  };
  hit.addEventListener("mousemove", (e) => showAt(nearest(e)));
  hit.addEventListener("mouseleave", hideTip);
}

function setupControls() {
  $("group").innerHTML = DATA.groups.map((g) => `<option value="${g.id}">${g.label}</option>`).join("");
  const sync = () => {
    $("group").value = state.g; $("view").value = state.view; $("agg").value = state.agg; $("ma").value = String(state.ma);
    $("from").value = state.from; $("to").value = state.to; $("ev").checked = state.ev; $("br").checked = state.br;
    $("from").min = $("to").min = DATA.dates[0]; $("from").max = $("to").max = DATA.dates[DATA.dates.length - 1];
    const group = DATA.groups.find((g) => g.id === state.g);
    $("seriesToggles").innerHTML = group.series.map((s, i) =>
      `<label><input type="checkbox" data-key="${s.key}" ${state.hide.has(s.key) ? "" : "checked"}><i class="swatch" style="background:var(${COLORS[i]})"></i>${s.label}</label>`).join("");
    $("seriesToggles").querySelectorAll("input").forEach((el) => el.addEventListener("change", () => {
      el.checked ? state.hide.delete(el.dataset.key) : state.hide.add(el.dataset.key); update();
    }));
  };
  const update = () => { writeURL(); render(); };
  $("group").addEventListener("change", (e) => { state.g = e.target.value; state.hide.clear(); sync(); update(); });
  $("view").addEventListener("change", (e) => { state.view = e.target.value; update(); });
  $("agg").addEventListener("change", (e) => { state.agg = e.target.value; update(); });
  $("ma").addEventListener("change", (e) => { state.ma = +e.target.value; update(); });
  $("from").addEventListener("change", (e) => { if (e.target.value) { state.from = e.target.value; update(); } });
  $("to").addEventListener("change", (e) => { if (e.target.value) { state.to = e.target.value; update(); } });
  $("ev").addEventListener("change", (e) => { state.ev = e.target.checked; update(); });
  $("br").addEventListener("change", (e) => { state.br = e.target.checked; update(); });
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    const last = DATA.dates[DATA.dates.length - 1];
    const p = b.dataset.preset;
    state.to = last;
    state.from = p === "all" ? DATA.dates[0] : p === "2025" ? "2025-01-01" : p === "52" ? DATA.dates[DATA.dates.length - 52] : "2026-03-01";
    sync(); update();
  }));
  $("chart").addEventListener("keydown", (e) => {
    if (!geom) return;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      showAt((geom.idx === null ? geom.dates.length - 1 : geom.idx) + (e.key === "ArrowRight" ? 1 : -1));
    } else if (e.key === "Escape") hideTip();
  });
  $("chart").addEventListener("blur", hideTip);
  sync();
}

readURL();
setupControls();
render();
// ?at=YYYY-MM-DD 가 있으면 그 시점의 툴팁을 띄운다(스크린샷·공유용)
try {
  const at = new URLSearchParams(location.search).get("at");
  if (at && geom) {
    const i = geom.dates.findIndex((d) => d >= at);
    if (i >= 0) showAt(i);
  }
} catch (e) { /* 무시 */ }
$("footer").textContent = "출처: " + DATA.source + ". Google Trends 값은 요청마다 '기간 안 최댓값 = 100' 으로 정규화한 상대 지수다.";
let rt;
window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 120); });
</script>
</body>
</html>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(build_payload(), ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    print(f"대시보드 생성: {OUT.relative_to(BASE)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
