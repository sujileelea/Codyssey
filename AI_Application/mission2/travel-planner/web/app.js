/* 국내 여행 추천 — 로컬 웹 화면 (순수 JS)
 *
 * POST /api/plan 의 진행 이벤트 스트림(NDJSON)을 읽어 단계 표시·로그를 갱신하고,
 * 마지막 result 이벤트로 리포트·지도·오류 안내를 그린다. 저장된 결과는 GET /api/results 로 다시 본다.
 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const STEP_LABELS = { recommend: "1차 추천", place_search: "맛집 검색", report: "리포트", save: "저장" };
const CITY_COLORS = ["--city-0", "--city-1", "--city-2"];
const KOREA_CENTER = { lat: 36.4, lng: 127.8 };

const state = { config: null, current: null, running: false, timer: null };

/* ---------- 공통 ---------- */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function cityColor(index) {
  return getComputedStyle(document.documentElement).getPropertyValue(CITY_COLORS[index % CITY_COLORS.length]).trim();
}

function isoDate(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function getJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* ---------- Markdown → HTML (리포트에 쓰는 문법만, 먼저 이스케이프해 HTML 주입을 막는다) ---------- */

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function inline(text) {
  return escapeHtml(text)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderMarkdown(md) {
  const out = [];
  let list = null;
  let para = [];
  let cityIndex = 0;
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const openList = (tag) => { if (list !== tag) { closeList(); out.push(`<${tag}>`); list = tag; } };

  md.split(/\r?\n/).forEach((rawLine, i) => {
    const line = rawLine.trimEnd();
    let m;
    if (!line.trim()) { flushPara(); closeList(); return; }
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      flushPara(); closeList();
      if (m[1].length === 1 && i === 0) return;              // 제목은 결과 머리말에 이미 있음
      const level = Math.min(m[1].length + 1, 6);            // 페이지 제목 구조에 맞춰 한 단계 내림
      const isCity = m[1].length === 2 && /^\d+\.\s*/.test(m[2]);
      const id = isCity ? ` id="city-${cityIndex++}" tabindex="-1"` : "";
      out.push(`<h${level}${id}>${inline(m[2])}</h${level}>`);
      return;
    }
    if ((m = line.match(/^\s*[-*]\s+(.*)$/))) { flushPara(); openList("ul"); out.push(`<li>${inline(m[1])}</li>`); return; }
    if ((m = line.match(/^\s*\d+\.\s+(.*)$/))) { flushPara(); openList("ol"); out.push(`<li>${inline(m[1])}</li>`); return; }
    if ((m = line.match(/^>\s?(.*)$/))) { flushPara(); closeList(); out.push(`<blockquote>${inline(m[1])}</blockquote>`); return; }
    closeList();
    para.push(line.trim());
  });
  flushPara();
  closeList();
  return out.join("\n");
}

/* ---------- 지도: 카카오맵 우선, 실패하면 Leaflet + OpenStreetMap ---------- */

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = el("script", { src, async: true });
    s.onload = resolve;
    s.onerror = () => reject(new Error(`스크립트를 불러오지 못함: ${src}`));
    document.head.append(s);
  });
}

function loadStyle(href) {
  document.head.append(el("link", { rel: "stylesheet", href }));
}

function pinElement(number, color, label, tag = "button") {
  // 카카오맵은 핀 자체가 버튼, Leaflet 은 마커가 이미 포커스 가능한 요소라 span 으로 만든다
  const attrs = tag === "button" ? { type: "button", class: "pin", "aria-label": label, title: label } : { class: "pin" };
  const pin = el(tag, attrs, el("span", { text: number }));
  pin.style.setProperty("--pin", color);
  return pin;
}

function popupElement(place) {
  return el("div", { class: "pin-popup" },
    el("strong", {}, place.url ? el("a", { href: place.url, target: "_blank", rel: "noopener noreferrer", text: place.name }) : place.name),
    place.category ? el("div", { text: place.category.split(" > ").slice(-1)[0] }) : null,
    place.address ? el("div", { text: place.address }) : null);
}

const MapView = {
  kind: null,        // "kakao" | "leaflet" | null(지도 없음)
  map: null,
  items: [],         // { city, index, place, show(), hide(), open() }
  ready: null,

  init(container) {
    if (!this.ready) this.ready = this._load(container);
    return this.ready;
  },

  async _load(container) {
    const key = state.config && state.config.kakao_js_key;
    if (key) {
      try {
        await loadScript(`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`);
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("카카오 지도 초기화 시간 초과")), 6000);
          window.kakao.maps.load(() => { clearTimeout(timeout); resolve(); });
        });
        const center = new kakao.maps.LatLng(KOREA_CENTER.lat, KOREA_CENTER.lng);
        this.map = new kakao.maps.Map(container, { center, level: 13 });
        this.map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
        this.popup = new kakao.maps.CustomOverlay({ yAnchor: 1, zIndex: 3 });
        this.kind = "kakao";
        return "카카오맵";
      } catch (err) {
        console.warn("카카오 지도 실패 → OpenStreetMap 으로 대체:", err);
        container.replaceChildren();
      }
    }
    try {
      loadStyle("https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css");
      await loadScript("https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js");
      this.map = L.map(container, { scrollWheelZoom: false }).setView([KOREA_CENTER.lat, KOREA_CENTER.lng], 7);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
      }).addTo(this.map);
      this.kind = "leaflet";
      return key ? "OpenStreetMap (카카오 지도 실패 → 대체)" : "OpenStreetMap";
    } catch (err) {
      console.warn("지도를 불러오지 못함:", err);
      this.kind = null;
      container.replaceChildren(el("div", { class: "map-fallback", text: "지도를 불러오지 못했습니다 (인터넷 연결 확인). 아래 목록은 그대로 볼 수 있습니다." }));
      return "지도 없음";
    }
  },

  clear() {
    for (const item of this.items) item.hide();
    this.items = [];
    if (this.kind === "kakao") this.popup.setMap(null);
    if (this.kind === "leaflet") this.map.closePopup();
  },

  render(groups) {
    this.clear();
    if (!this.kind) return;
    groups.forEach((group) => {
      group.places.forEach((place, i) => {
        if (typeof place.x !== "number" || typeof place.y !== "number") return;
        const label = `${group.city} ${i + 1}. ${place.name}`;
        const pin = pinElement(i + 1, group.color, label, this.kind === "kakao" ? "button" : "span");
        const item = { city: group.index, index: i, place };
        if (this.kind === "kakao") {
          const position = new kakao.maps.LatLng(place.y, place.x);
          const overlay = new kakao.maps.CustomOverlay({ position, content: pin, yAnchor: 1, clickable: true });
          item.position = position;
          item.show = () => overlay.setMap(this.map);
          item.hide = () => overlay.setMap(null);
          item.open = () => {
            const box = el("div", { class: "kakao-popup" }, popupElement(place));
            this.popup.setContent(box);
            this.popup.setPosition(position);
            this.popup.setMap(this.map);
            this.map.panTo(position);
          };
          pin.addEventListener("click", () => { item.open(); highlightPlace(group.index, i); });
        } else {
          const icon = L.divIcon({ className: "pin-icon", html: pin.outerHTML, iconSize: [26, 26], iconAnchor: [13, 31], popupAnchor: [0, -30] });
          const marker = L.marker([place.y, place.x], { icon, title: label, alt: label, keyboard: true }).bindPopup(popupElement(place));
          marker.on("click", () => highlightPlace(group.index, i));
          item.position = [place.y, place.x];
          item.show = () => marker.addTo(this.map);
          item.hide = () => marker.remove();
          item.open = () => { this.map.panTo(item.position); marker.openPopup(); };
        }
        item.show();
        this.items.push(item);
      });
    });
    this.filter(null);
  },

  filter(cityIndex) {
    const visible = this.items.filter((item) => cityIndex === null || item.city === cityIndex);
    for (const item of this.items) (visible.includes(item) ? item.show : item.hide)();
    if (this.kind === "kakao") this.popup.setMap(null);
    this.fit(visible);
  },

  fit(items) {
    if (!this.kind) return;
    if (this.kind === "kakao") {
      this.map.relayout();
      if (!items.length) { this.map.setCenter(new kakao.maps.LatLng(KOREA_CENTER.lat, KOREA_CENTER.lng)); this.map.setLevel(13); return; }
      const bounds = new kakao.maps.LatLngBounds();
      items.forEach((item) => bounds.extend(item.position));
      this.map.setBounds(bounds);
      if (items.length === 1) this.map.setLevel(4);
    } else {
      this.map.invalidateSize();
      if (!items.length) { this.map.setView([KOREA_CENTER.lat, KOREA_CENTER.lng], 7); return; }
      this.map.fitBounds(L.latLngBounds(items.map((item) => item.position)), { padding: [28, 28], maxZoom: 15 });
    }
  },

  focus(cityIndex, index) {
    const item = this.items.find((it) => it.city === cityIndex && it.index === index);
    if (item) item.open();
  },
};

/* ---------- 결과 그리기 ---------- */

function cityGroups(raw) {
  const cities = (raw.recommendation && raw.recommendation.recommended_cities) || [];
  return cities.map((c, index) => ({
    index, city: c.city, color: cityColor(index), places: (raw.places && raw.places[c.city]) || [],
  }));
}

function renderAlerts(payload) {
  const box = $("#alerts");
  box.replaceChildren();
  if (!payload.ok) {
    box.append(el("div", { class: "alert fail", role: "alert" },
      el("h3", { text: "1차 추천을 만들지 못했습니다" }),
      el("p", { text: "다음 단계의 입력(추천 지역)이 없어 리포트를 만들지 않았습니다. 아래 오류 안내를 확인한 뒤 다시 시도하세요." })));
  }
  if (payload.saved === false) {
    box.append(el("div", { class: "alert fail", role: "alert" },
      el("h3", { text: "결과 파일을 저장하지 못했습니다" }),
      el("p", { text: "화면의 리포트는 그대로입니다. 위의 저장 버튼으로 내려받으세요." })));
  }
  if (payload.errors.length) {
    box.append(el("div", { class: payload.ok ? "alert warn" : "alert fail" },
      el("h3", { text: `오류 ${payload.errors.length}건 — 실패한 부분은 '데이터 없음'으로 두고 계속 진행했습니다` }),
      el("ul", {}, payload.errors.map((e) => el("li", {},
        el("span", { class: "badge warn", text: e.type }), " ",
        el("strong", { text: STEP_LABELS[e.step] || e.step }), ` — ${e.message}`,
        e.hint ? el("span", { class: "hint", text: `→ ${e.hint}` }) : null)))));
  }
}

function renderPlaces(groups) {
  const box = $("#places");
  box.replaceChildren();
  groups.forEach((group) => {
    box.append(el("h4", {},
      el("span", { class: "list-pin", style: `--pin:${group.color}`, "aria-hidden": "true" }),
      `${group.index + 1}. ${group.city}`,
      el("a", { href: `#city-${group.index}`, text: "일정 보기",
        onclick: (ev) => { ev.preventDefault(); const h = document.getElementById(`city-${group.index}`); if (h) { h.scrollIntoView({ behavior: "smooth", block: "start" }); h.focus({ preventScroll: true }); } } })));
    if (!group.places.length) {
      box.append(el("p", { class: "no-data", text: "데이터 없음 (장소 검색 결과 0건)" }));
      return;
    }
    box.append(el("ol", {}, group.places.map((place, i) => el("li", { class: "place", "data-city": group.index, "data-index": i },
      el("span", { class: "list-pin", style: `--pin:${group.color}`, "aria-hidden": "true", text: i + 1 }),
      el("div", { class: "place-body" },
        el("div", { class: "place-name" },
          place.url ? el("a", { href: place.url, target: "_blank", rel: "noopener noreferrer", text: place.name }) : place.name),
        el("div", { class: "place-sub", text: [place.category && place.category.split(" > ").slice(-1)[0], place.address].filter(Boolean).join(" · ") })),
      typeof place.x === "number" && MapView.kind
        ? el("button", { type: "button", class: "ghost", "aria-label": `${place.name} 지도에서 보기`, text: "지도",
            onclick: () => { MapView.focus(group.index, i); highlightPlace(group.index, i); } })
        : null))));
  });
}

function highlightPlace(cityIndex, index) {
  document.querySelectorAll(".place.is-active").forEach((n) => n.classList.remove("is-active"));
  const node = document.querySelector(`.place[data-city="${cityIndex}"][data-index="${index}"]`);
  if (node) { node.classList.add("is-active"); node.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
}

function renderFilter(groups) {
  const box = $("#city-filter");
  box.replaceChildren();
  if (groups.length < 2) return;
  const buttons = [];
  const choose = (cityIndex, button) => {
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    MapView.filter(cityIndex);
  };
  const all = el("button", { type: "button", "aria-pressed": "true", text: "전체" });
  all.addEventListener("click", () => choose(null, all));
  buttons.push(all);
  groups.forEach((group) => {
    const b = el("button", { type: "button", "aria-pressed": "false" },
      el("span", { class: "swatch", style: `background:${group.color}`, "aria-hidden": "true" }), group.city);
    b.addEventListener("click", () => choose(group.index, b));
    buttons.push(b);
  });
  box.append(...buttons);
}

async function renderResult(payload) {
  state.current = payload;
  $("#welcome").hidden = true;
  $("#result").hidden = false;

  const raw = payload.raw;
  const groups = cityGroups(raw);
  $("#result-title").textContent = `${payload.date} 여행 추천`;
  const source = payload.source === "saved" ? "저장된 결과" : payload.cached ? "새 리포트 (저장된 추천·맛집 재사용)" : "새로 생성";
  $("#result-meta").textContent = [
    groups.map((g) => g.city).join(" · "),
    formatTime(raw.generated_at),
    raw.llm_model,
    source,
  ].filter(Boolean).join("  ·  ");

  renderAlerts(payload);
  $("#dl-md").disabled = !payload.markdown;
  $("#report").innerHTML = payload.markdown
    ? renderMarkdown(payload.markdown)
    : '<p class="empty-note">리포트가 없습니다.</p>';

  $("#result-title").focus();
  renderFilter(groups);
  const note = await MapView.init($("#map"));
  $("#map-note").textContent = note;
  renderPlaces(groups);
  MapView.render(groups);
  markHistory(payload.date);
}

/* ---------- 진행 상황 ---------- */

function resetProgress() {
  $("#progress").hidden = false;
  $("#log").replaceChildren();
  document.querySelectorAll(".steps li").forEach((li) => setStep(li, "is-wait", "대기"));
  const started = Date.now();
  clearInterval(state.timer);
  $("#elapsed").textContent = "";
  state.timer = setInterval(() => { $("#elapsed").textContent = `${Math.round((Date.now() - started) / 1000)}초`; }, 500);
}

function setStep(li, cls, text) {
  li.className = cls;
  li.querySelector(".state").textContent = text;
}

function stepNode(n) {
  return document.querySelector(`.steps li[data-step="${n}"]`);
}

function finishRunningSteps() {
  document.querySelectorAll(".steps li.is-run").forEach((li) => setStep(li, "is-done", "완료"));
}

function addLog(step, level, text) {
  const tag = step ? `[${step}/3]` : "·";
  $("#log").append(el("li", { class: level === "info" ? null : level },
    el("span", { class: "tag", text: tag }), el("span", { text })));
  $("#log").scrollTop = $("#log").scrollHeight;
}

function handleEvent(event) {
  if (event.kind === "step") {
    finishRunningSteps();
    const li = stepNode(event.step);
    const cached = event.title.includes("(캐시)");
    setStep(li, cached ? "is-cache" : "is-run", cached ? "캐시" : "진행 중");
    addLog(event.step, "info", event.title);
  } else if (event.kind === "log") {
    const li = stepNode(event.step);
    if (event.level === "error") setStep(li, "is-fail", "실패");
    else if (event.level === "warn" && !li.classList.contains("is-fail")) setStep(li, "is-warn", "경고");
    addLog(event.step, event.level, event.text);
  } else if (event.kind === "notice") {
    addLog(null, event.level, event.text);
  } else if (event.kind === "fatal") {
    document.querySelectorAll(".steps li.is-run").forEach((li) => setStep(li, "is-fail", "실패"));
    addLog(null, "error", event.text);
    showFormError(event.text);
  } else if (event.kind === "result") {
    finishRunningSteps();
    return event;
  }
  return null;
}

/* ---------- 입력 검증 ---------- */

function showFieldError(field, message) {
  const input = field === "cities" ? null : $(`#${field}`);
  const box = $(`#${field}-error`);
  if (!box) return showFormError(message);
  box.textContent = message;
  box.hidden = !message;
  if (input) input.setAttribute("aria-invalid", message ? "true" : "false");
  if (message && input) input.focus();
}

function showFormError(message) {
  $("#form-error").textContent = message || "";
  $("#form-error").hidden = !message;
}

function clearErrors() {
  ["date", "cities", "count"].forEach((f) => showFieldError(f, ""));
  showFormError("");
}

function readForm() {
  const date = $("#date").value.trim();
  const count = Number($("#count").value);
  const cities = Number(document.querySelector('input[name="cities"]:checked').value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    showFieldError("date", "여행 날짜를 골라 주세요 (YYYY-MM-DD)");
    return null;
  }
  if (!Number.isInteger(count) || count < 1 || count > 15) {
    showFieldError("count", "맛집 수는 1~15 사이 정수로 입력하세요");
    return null;
  }
  return { date, cities, count, no_cache: $("#no-cache").checked };
}

function setRunning(running) {
  state.running = running;
  $("#form-fields").disabled = running;
  $("#submit").disabled = running;
  $("#submit").setAttribute("aria-busy", String(running));
  $("#submit .label").textContent = running ? "생성 중… (보통 10~30초)" : "추천 받기";
  if (!running) clearInterval(state.timer);
}

async function runPlan(params) {
  setRunning(true);
  resetProgress();
  let result = null;
  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      $("#progress").hidden = true;
      if (data.field) showFieldError(data.field, data.error);
      else showFormError(data.error || `요청 실패 (HTTP ${res.status})`);
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (!line) continue;
        try {
          result = handleEvent(JSON.parse(line)) || result;
        } catch (err) {
          console.warn("이벤트 해석 실패:", line, err);
        }
      }
      if (done) break;
    }
    if (result) {
      await renderResult(result);
    } else if ($("#form-error").hidden) {
      showFormError("결과를 받지 못하고 연결이 끝났습니다. 서버 터미널을 확인하거나 '저장된 결과'에서 확인하세요.");
    }
  } catch (err) {
    showFormError(`서버에 연결할 수 없습니다 — 터미널에서 python3 web.py 가 실행 중인지 확인하세요. (${err.message})`);
  } finally {
    setRunning(false);
    loadHistory();
  }
}

/* ---------- 저장된 결과 ---------- */

function markHistory(date) {
  document.querySelectorAll("#history button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.date === date)));
}

async function loadHistory() {
  const list = $("#history");
  try {
    const { results } = await getJSON("/api/results");
    list.replaceChildren();
    if (!results.length) {
      list.append(el("li", { class: "empty", text: "아직 저장된 결과가 없습니다" }));
      return;
    }
    for (const item of results) {
      const sub = item.broken
        ? "파일을 읽을 수 없음"
        : item.ok ? `${item.cities.join(" · ")} · 맛집 ${item.places}곳` : "1차 추천 실패 기록";
      const badge = item.broken || !item.ok
        ? el("span", { class: "badge fail", text: "실패" })
        : item.errors ? el("span", { class: "badge warn", text: `오류 ${item.errors}` }) : null;
      const button = el("button", { type: "button", "data-date": item.date, disabled: item.broken || null },
        el("span", { class: "h-date" }, item.date, " ", badge),
        el("span", { class: "h-sub", text: sub }));
      button.addEventListener("click", () => openSaved(item.date));
      list.append(el("li", {}, button));
    }
    if (state.current) markHistory(state.current.date);
  } catch (err) {
    list.replaceChildren(el("li", { class: "empty", text: `목록을 불러오지 못했습니다 (${err.message})` }));
  }
}

async function openSaved(date) {
  if (state.running) return;
  clearErrors();
  try {
    $("#progress").hidden = true;
    await renderResult(await getJSON(`/api/results/${encodeURIComponent(date)}`));
  } catch (err) {
    showFormError(`저장된 결과를 열지 못했습니다: ${err.message}`);
  }
}

/* ---------- 시작 ---------- */

async function init() {
  const nextWeek = new Date();
  nextWeek.setDate(nextWeek.getDate() + 7);
  $("#date").value = isoDate(nextWeek);

  try {
    state.config = await getJSON("/api/config");
    $("#count").max = state.config.max_count;
    $("#count-help").textContent = `1~${state.config.max_count}곳 · 모델 ${state.config.model}`;
  } catch (err) {
    showFormError(`서버 설정을 불러오지 못했습니다 — python3 web.py 가 실행 중인지 확인하세요. (${err.message})`);
  }

  $("#plan-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    if (state.running) return;
    clearErrors();
    const params = readForm();
    if (params) runPlan(params);
  });
  ["date", "count"].forEach((f) => $(`#${f}`).addEventListener("input", () => showFieldError(f, "")));
  $("#history-refresh").addEventListener("click", loadHistory);
  $("#dl-md").addEventListener("click", () => {
    const p = state.current;
    if (p && p.markdown) download(`${p.date}_travel_plan.md`, p.markdown, "text/markdown;charset=utf-8");
  });
  $("#dl-json").addEventListener("click", () => {
    const p = state.current;
    if (p) download(`${p.date}_raw.json`, JSON.stringify(p.raw, null, 2), "application/json;charset=utf-8");
  });
  loadHistory();
}

init();
