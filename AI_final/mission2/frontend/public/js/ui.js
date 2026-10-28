// 화면 공통 도구 — DOM 만들기(문자열은 항상 textContent 로), 숫자 · 날짜 표기, 알림.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export const $ = (id) => document.getElementById(id);

export function fmt(x, digits = 2) {
  if (x == null || Number.isNaN(x)) return "-";
  const n = Number(x);
  return Number.isInteger(n) ? n.toLocaleString("ko-KR") : n.toLocaleString("ko-KR", { maximumFractionDigits: digits });
}

export function pct(x) {
  if (x == null) return "-";
  return (x > 0 ? "+" : "") + fmt(x, 1) + "%";
}

export function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const sec = (Date.now() - d.getTime()) / 1000;
  if (sec < 60) return "방금";
  if (sec < 3600) return Math.floor(sec / 60) + "분 전";
  if (sec < 86400) return Math.floor(sec / 3600) + "시간 전";
  return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

let toastTimer;
export function toast(message, isError = false) {
  const t = $("toast");
  t.textContent = message;
  t.classList.toggle("err", isError);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 5000 : 2600);
}

// 브라우저 저장소는 개인 편의(테마 · 마지막 탭)에만 쓰고, 막혀 있어도 동작하게 한다
export const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* 무시 */ } },
};

// 두 번 눌러야 지워지는 버튼(브라우저 확인창 대신)
export function confirmClick(button, label, action) {
  if (button.dataset.armed) {
    delete button.dataset.armed;
    action();
    return;
  }
  const original = button.textContent;
  button.dataset.armed = "1";
  button.classList.add("confirm");
  button.textContent = label;
  setTimeout(() => {
    if (!button.isConnected) return;
    delete button.dataset.armed;
    button.classList.remove("confirm");
    button.textContent = original;
  }, 3000);
}
