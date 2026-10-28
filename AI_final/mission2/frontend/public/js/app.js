// 시작점 — 테마 · 탭 · 서버 깨우기(콜드스타트) 후 각 화면을 연다.
import { api, apiBase } from "./api.js";
import { refresh } from "./state.js";
import { initSummary } from "./summary.js";
import { $, store, toast } from "./ui.js";

// ── 다크 모드 ──
function currentTheme() {
  const set = document.documentElement.dataset.theme;
  if (set) return set;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $("theme-toggle");
  btn.setAttribute("aria-label", theme === "dark" ? "라이트 모드 켜기" : "다크 모드 켜기");
  btn.title = theme === "dark" ? "라이트 모드" : "다크 모드";
  store.set("theme", theme);
  window.dispatchEvent(new Event("themechange"));
}
$("theme-toggle").addEventListener("click", () => applyTheme(currentTheme() === "dark" ? "light" : "dark"));

// ── 탭 ──
const tabs = [$("tab-chat"), $("tab-data")];
function selectTab(tab, focus = false) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  }
  if (focus) tab.focus();
  store.set("tab", tab.id);
  window.dispatchEvent(new CustomEvent("tabchange", { detail: tab.id }));
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      selectTab(tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length], true);
    }
  });
});
const params = new URLSearchParams(location.search);
const startTab = params.get("tab") === "data" ? "tab-data" : params.get("tab") === "chat" ? "tab-chat" : store.get("tab");
if (startTab === "tab-data") selectTab($("tab-data"));

$("docs-link").href = apiBase + "/docs";

// ── 서버 깨우기 ──
// Render 무료 서버는 15분 동안 요청이 없으면 잠든다. 첫 요청이 오래 걸리면 안내를 띄우고 깨어날 때까지 다시 묻는다.
function setStatus(kind, label) {
  const s = $("server-status");
  s.className = "status " + kind;
  s.querySelector(".label").textContent = label;
}

export async function wakeServer() {
  const started = Date.now();
  const banner = $("wake-banner");
  const tick = setInterval(() => { $("wake-sec").textContent = Math.round((Date.now() - started) / 1000); }, 1000);
  const slow = setTimeout(() => { banner.hidden = false; setStatus("waking", "서버 깨우는 중"); }, 2500);
  try {
    while (true) {
      try {
        const h = await api.health(20000);
        setStatus("ok", "서버 연결됨");
        return h;
      } catch (e) {
        if (Date.now() - started > 120000) {
          setStatus("down", "서버 연결 실패");
          throw e;
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  } finally {
    clearTimeout(slow);
    clearInterval(tick);
    banner.hidden = true;
  }
}

async function start() {
  initSummary();
  try {
    const health = await wakeServer();
    if (health.dataset_name) $("dataset-name").textContent = health.dataset_name;
  } catch (e) {
    $("dataset-name").textContent = "서버에 연결하지 못했습니다 — 새로 고침해 주세요.";
    return;
  }
  try {
    await refresh();
  } catch (e) {
    toast(e.message, true);
    $("summary-body").replaceChildren(document.createTextNode(e.message));
  }
}

start();
