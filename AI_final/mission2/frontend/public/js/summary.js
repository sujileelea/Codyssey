// 데이터 요약 패널 — GET /api/data/summary 결과(= AI 에 주입되는 요약)를 그대로 보여 준다.
import { api } from "./api.js";
import { autoResize, lineChart } from "./chart.js";
import { state, subscribe, refresh } from "./state.js";
import { $, el, fmt, pct, toast } from "./ui.js";

function trendBadge(t, title) {
  const cls = t.direction === "상승" ? "up" : t.direction === "하락" ? "down" : "";
  const arrow = t.direction === "상승" ? "▲" : t.direction === "하락" ? "▼" : "■";
  return el("div", {},
    el("div", { class: `trend-badge ${cls}` }, el("span", { text: title }), el("b", { text: `${arrow} ${t.direction}` }),
      t.change_pct != null ? el("span", { text: pct(t.change_pct) }) : null),
    t.window ? el("p", { class: "trend-note", text: `최근 ${t.window}개 평균 ${fmt(t.recent_avg)} · 직전 ${t.window}개 평균 ${fmt(t.previous_avg)}` }) : null);
}

function render(s) {
  const body = $("summary-body");
  if (!s) return;
  if (!s.count) {
    body.replaceChildren(el("p", { class: "muted", text: "저장된 데이터가 없습니다. 데이터 관리 탭에서 추가해 주세요." }));
    return;
  }
  const m = s.metrics;
  const row = (k, v) => [el("dt", { text: k }), el("dd", { text: v })];
  body.replaceChildren(
    el("dl", { class: "kv" },
      row("기간", s.period),
      row("개수", `${fmt(s.count)}개 · ${s.interval.split("(")[0]}`),
      row("평균 · 중앙값", `${fmt(m.average)} · ${fmt(m.median)}`),
      row("최댓값", `${fmt(m.max)} (${m.max_date})`),
      row("최솟값", `${fmt(m.min)} (${m.min_date})`),
      row("합계", fmt(m.total)),
      row("최신 값", `${fmt(s.latest.value)} (${s.latest.date})`)),
    trendBadge(s.trend_detail, "단기 추세"),
    trendBadge(s.trend_long, "장기 추세"),
  );
}

function drawMini() {
  lineChart($("mini-chart"), state.points, { mini: true, label: "전체 기간 값 추이(미니 그래프)" });
}

async function loadPrompt() {
  const pre = $("prompt-text");
  try {
    const p = await api.prompt();
    pre.textContent = p.system_prompt;
  } catch (e) {
    pre.textContent = "불러오지 못했습니다: " + e.message;
  }
}

export function initSummary() {
  subscribe((st) => {
    render(st.summary);
    drawMini();
    if ($("prompt-text").closest("details").open) loadPrompt();
  });
  autoResize($("mini-chart"), drawMini);
  $("prompt-text").closest("details").addEventListener("toggle", (e) => { if (e.target.open) loadPrompt(); });
  $("summary-refresh").addEventListener("click", async () => {
    try {
      await refresh();
      toast("요약을 새로 고쳤습니다.");
    } catch (e) {
      toast(e.message, true);
    }
  });
}
