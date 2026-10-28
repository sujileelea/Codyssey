// 데이터 관리 — 추가 · 수정 · 삭제(CRUD), 지표 타일 · 그래프(통계 API), 내보내기(CSV · JSON).
import { api } from "./api.js";
import { autoResize, lineChart } from "./chart.js";
import { refresh, state, subscribe } from "./state.js";
import { $, confirmClick, el, fmt, pct, toast } from "./ui.js";

let stats = null;
let editingId = null;
let flashId = null;

// ── 지표 타일 + 그래프 ──
async function loadStatistics() {
  try {
    stats = await api.statistics(Number($("ma-window").value));
  } catch (e) {
    stats = null;
    toast(e.message, true);
  }
  renderTiles();
  drawChart();
}

function tile(label, value, sub) {
  return el("div", { class: "tile" }, el("div", { class: "t-label", text: label }), el("div", { class: "t-value", text: value }),
    sub ? el("div", { class: "t-sub", text: sub }) : null);
}

function renderTiles() {
  const box = $("stat-tiles");
  const s = state.summary;
  if (!s || !s.count || !stats) {
    box.replaceChildren();
    return;
  }
  const lastYear = stats.yearly[stats.yearly.length - 1];
  box.replaceChildren(
    tile("최신 값", fmt(s.latest.value), s.latest.date),
    tile("전년 같은 시기 대비", stats.yoy ? pct(stats.yoy.change_pct) : "-",
      stats.yoy ? `${stats.yoy.year_ago_date} ${fmt(stats.yoy.year_ago_value)} → ${fmt(stats.yoy.value)}` : "1년 전 값 없음"),
    tile("최고점 대비", pct(stats.from_peak_pct), `최고 ${fmt(s.metrics.max)} (${s.metrics.max_date})`),
    tile("최대 상승", stats.largest_rise ? pct(stats.largest_rise.change_pct) : "-",
      stats.largest_rise ? `${stats.largest_rise.date} · ${fmt(stats.largest_rise.from)} → ${fmt(stats.largest_rise.to)}` : ""),
    tile("최대 하락", stats.largest_drop ? pct(stats.largest_drop.change_pct) : "-",
      stats.largest_drop ? `${stats.largest_drop.date} · ${fmt(stats.largest_drop.from)} → ${fmt(stats.largest_drop.to)}` : ""),
    tile("변동성(최근 13개)", stats.volatility ? `±${fmt(stats.volatility.recent_std_change_pct, 1)}%` : "-",
      stats.volatility ? `전체 ±${fmt(stats.volatility.std_change_pct, 1)}% · 직전 대비 변화율의 표준편차` : ""),
    tile(`${lastYear.year}년 평균`, fmt(lastYear.average), lastYear.change_pct != null ? `전년 대비 ${pct(lastYear.change_pct)}` : `${lastYear.count}개`),
    tile("연속 방향", stats.streak ? `${stats.streak.direction} ${stats.streak.length}회` : "변화 없음", "끝에서부터 같은 방향으로 움직인 횟수"),
  );
}

function drawChart() {
  if ($("view-data").hidden) return;              // 숨은 탭은 폭이 0 이라 보일 때 그린다
  const range = $("range").value;
  const maByDate = new Map((stats ? stats.moving_average.series : []).map((p) => [p.date, p.ma]));
  let points = state.points.map((p) => ({ ...p, ma: maByDate.get(p.date) ?? null }));
  if (range !== "all") points = points.slice(-Number(range));
  const w = $("ma-window").value;
  lineChart($("main-chart"), points, { maLabel: `이동평균(직전 ${w}개)`, label: `값과 ${w}개 이동평균 추이` });
  $("chart-caption").textContent = points.length
    ? `${points[0].date} ~ ${points[points.length - 1].date} · ${points.length}개 · 점 = 메모가 있는 시점(사건 · 급등 · 단절). 그래프 위에서 마우스를 움직이거나 그래프를 선택한 뒤 방향키로 값을 읽을 수 있고, 모든 값은 아래 표에도 있습니다.`
    : "";
}

// ── 표 ──
function rowNode(p) {
  if (p.id === editingId) {
    const date = el("input", { type: "date", value: p.date, "aria-label": "날짜" });
    const value = el("input", { type: "number", step: "any", value: p.value, "aria-label": "값" });
    const memo = el("input", { value: p.memo || "", maxlength: "200", "aria-label": "메모" });
    const save = el("button", { class: "btn small primary", type: "button", text: "저장" });
    const cancel = el("button", { class: "btn small ghost", type: "button", text: "취소" });
    save.addEventListener("click", () => update(p.id, { date: date.value, value: value.value, memo: memo.value }, save));
    cancel.addEventListener("click", () => { editingId = null; renderTable(); });
    const tr = el("tr", {}, el("td", {}, date), el("td", { class: "num" }, value), el("td", {}, memo), el("td", { class: "actions" }, save, " ", cancel));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") save.click(); if (e.key === "Escape") cancel.click(); });
    setTimeout(() => value.focus());
    return tr;
  }
  const edit = el("button", { class: "btn small ghost", type: "button", text: "수정", "aria-label": `${p.date} 수정` });
  const del = el("button", { class: "btn small ghost danger", type: "button", text: "삭제", "aria-label": `${p.date} 삭제` });
  edit.addEventListener("click", () => { editingId = p.id; renderTable(); });
  del.addEventListener("click", () => confirmClick(del, "삭제 확인", () => remove(p)));
  return el("tr", { class: p.id === flashId ? "flash" : null, "data-id": p.id },
    el("td", { text: p.date }), el("td", { class: "num", text: fmt(p.value) }), el("td", { text: p.memo || "" }),
    el("td", { class: "actions" }, edit, " ", del));
}

function renderTable() {
  const q = $("data-search").value.trim().toLowerCase();
  const rows = [...state.points].reverse().filter((p) => !q || p.date.includes(q) || (p.memo || "").toLowerCase().includes(q));
  const body = $("data-rows");
  body.replaceChildren(...(rows.length ? rows.map(rowNode) : [el("tr", {}, el("td", { colspan: "4", class: "muted", text: q ? "검색 결과가 없습니다." : "데이터가 없습니다." }))]));
  $("data-count").textContent = q ? `${rows.length} / ${state.points.length}개` : `${state.points.length}개`;
  if (flashId) {
    const tr = body.querySelector(`tr[data-id="${CSS.escape(flashId)}"]`);
    if (tr) tr.scrollIntoView({ block: "nearest" });
    flashId = null;
  }
}

// ── 쓰기 ──
function parseRow(raw) {
  const date = String(raw.date || "").trim();
  const value = String(raw.value ?? "").trim();
  const memo = String(raw.memo || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return { error: "날짜를 YYYY-MM-DD 로 입력해 주세요." };
  if (value === "" || !Number.isFinite(Number(value))) return { error: "값은 숫자로 입력해 주세요." };
  if (memo.length > 200) return { error: "메모는 200자 이하로 입력해 주세요." };
  return { row: { date, value: Number(value), memo } };
}

function formMessage(text, ok) {
  const msg = $("form-msg");
  msg.textContent = text;
  msg.className = "form-msg " + (ok ? "ok" : "err");
}

async function create(e) {
  e.preventDefault();
  const { row, error } = parseRow({ date: $("f-date").value, value: $("f-value").value, memo: $("f-memo").value });
  if (error) return formMessage(error, false);
  const btn = e.submitter || $("data-form").querySelector("button");
  btn.disabled = true;
  try {
    const saved = await api.createData(row);
    formMessage(`저장했습니다 — ${saved.date} = ${fmt(saved.value)}${saved.memo ? ` (${saved.memo})` : ""} · 요약과 AI 답변에 바로 반영됩니다.`, true);
    $("data-form").reset();
    flashId = saved.id;
    await refresh();
  } catch (err) {
    formMessage(err.message, false);
  } finally {
    btn.disabled = false;
  }
}

async function update(id, raw, btn) {
  const { row, error } = parseRow(raw);
  if (error) return toast(error, true);
  btn.disabled = true;
  try {
    const saved = await api.updateData(id, row);
    editingId = null;
    flashId = saved.id;
    toast(`수정했습니다 — ${saved.date} = ${fmt(saved.value)}`);
    await refresh();
  } catch (err) {
    btn.disabled = false;
    toast(err.message, true);
  }
}

async function remove(p) {
  try {
    await api.deleteData(p.id);
    toast(`삭제했습니다 — ${p.date} = ${fmt(p.value)}`);
    await refresh();
  } catch (err) {
    toast(err.message, true);
  }
}

// ── 내보내기 ──
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function stamp() {
  return new Date().toISOString().slice(0, 10).replaceAll("-", "");
}

function exportCsv() {
  const esc = (s) => (/[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s);
  const lines = ["date,value,memo", ...state.points.map((p) => [p.date, p.value, esc(p.memo || "")].join(","))];
  download(`my-data-${stamp()}.csv`, "﻿" + lines.join("\n") + "\n", "text/csv;charset=utf-8");   // BOM: 엑셀 한글
  toast(`CSV로 내보냈습니다 — ${state.points.length}행`);
}

function exportJson() {
  const body = { exported_at: new Date().toISOString(), summary: state.summary,
    data: state.points.map(({ date, value, memo }) => ({ date, value, memo })) };
  download(`my-data-${stamp()}.json`, JSON.stringify(body, null, 2), "application/json");
  toast(`JSON으로 내보냈습니다 — ${state.points.length}행 + 요약`);
}

export function initData() {
  subscribe(() => {
    renderTable();
    loadStatistics();
  });
  $("data-form").addEventListener("submit", create);
  $("data-search").addEventListener("input", renderTable);
  $("range").addEventListener("change", drawChart);
  $("ma-window").addEventListener("change", loadStatistics);
  $("export-csv").addEventListener("click", exportCsv);
  $("export-json").addEventListener("click", exportJson);
  $("f-date").value = new Date().toISOString().slice(0, 10);
  autoResize($("main-chart"), drawChart);
  window.addEventListener("tabchange", (e) => { if (e.detail === "tab-data") drawChart(); });
}
