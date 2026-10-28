// 선 그래프(SVG, 라이브러리 없음) — 값(계열 1) · 이동평균(계열 2) · 메모 시점 점.
// 축 하나, 얇은 선(2px), 연한 격자, 끝값 · 최고점만 직접 표기, 십자선 + 툴팁(마우스 · 방향키).
import { el, fmt } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  return n;
};

function niceStep(range, count) {
  const raw = range / Math.max(count, 1);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const norm = raw / mag;
  return (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
}

function compact(n) {
  const a = Math.abs(n);
  if (a >= 1e8) return fmt(n / 1e8, 1) + "억";
  if (a >= 1e4) return fmt(n / 1e4, 1) + "만";
  return fmt(n, 1);
}

const time = (d) => new Date(d + "T00:00:00Z").getTime();

/**
 * @param {HTMLElement} box
 * @param {{date:string,value:number,ma?:number|null,memo?:string}[]} points 날짜 오름차순
 * @param {{mini?:boolean, maLabel?:string, height?:number, label?:string}} opt
 */
export function lineChart(box, points, opt = {}) {
  box.replaceChildren();
  if (!points.length) {
    box.append(el("p", { class: "muted", text: "표시할 데이터가 없습니다." }));
    return;
  }
  const mini = !!opt.mini;
  const hasMA = !mini && points.some((p) => p.ma != null);
  const width = Math.max(box.clientWidth || 600, 260);
  const height = opt.height || (mini ? 120 : 300);
  const m = mini ? { t: 10, r: 34, b: 20, l: 6 } : { t: 16, r: 64, b: 28, l: 44 };
  const W = width - m.l - m.r;
  const H = height - m.t - m.b;

  // 범례(계열 2개 이상일 때)
  if (hasMA || (!mini && points.some((p) => p.memo))) {
    const legend = el("div", { class: "legend" },
      el("span", {}, el("i", { style: "background:var(--series-1)" }), "값"));
    if (hasMA) legend.append(el("span", {}, el("i", { style: "background:var(--series-2)" }), opt.maLabel || "이동평균"));
    if (points.some((p) => p.memo)) legend.append(el("span", {}, el("i", { class: "dot", style: "background:var(--series-1)" }), "메모 있는 시점"));
    box.append(legend);
  }

  const xs = points.map((p) => time(p.date));
  const x0 = xs[0], x1 = xs[xs.length - 1] === x0 ? x0 + 86400000 : xs[xs.length - 1];
  const vals = points.flatMap((p) => (p.ma != null && hasMA ? [p.value, p.ma] : [p.value]));
  let lo = Math.min(0, ...vals), hi = Math.max(...vals);
  if (hi === lo) hi = lo + 1;
  const step = niceStep(hi - lo, mini ? 2 : 4);
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;
  const X = (t) => m.l + ((t - x0) / (x1 - x0)) * W;
  const Y = (v) => m.t + H - ((v - lo) / (hi - lo)) * H;

  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img",
    "aria-label": opt.label || `값 추이 그래프, ${points[0].date}부터 ${points[points.length - 1].date}까지 ${points.length}개` });

  // 격자 · 축
  const grid = svg("g", { class: "grid" });
  for (let v = lo; v <= hi + step / 2; v += step) {
    grid.append(svg("line", { x1: m.l, x2: m.l + W, y1: Y(v), y2: Y(v) }));
    if (!mini) {
      const t = svg("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" });
      t.textContent = compact(v);
      root.append(t);
    }
  }
  root.prepend(grid);
  const axis = svg("g", { class: "axis" });
  axis.append(svg("line", { x1: m.l, x2: m.l + W, y1: Y(Math.max(lo, 0)), y2: Y(Math.max(lo, 0)) }));
  root.append(axis);

  // x 눈금 — 기간이 길면 연도, 짧으면 분기 첫 달
  const spanYears = (x1 - x0) / (365.25 * 86400000);
  const first = new Date(x0), last = new Date(x1);
  const ticks = [];
  for (let y = first.getUTCFullYear(); y <= last.getUTCFullYear(); y++) {
    for (const mo of spanYears > 2.5 ? [0] : spanYears > 0.8 ? [0, 3, 6, 9] : [...Array(12).keys()]) {
      const t = Date.UTC(y, mo, 1);
      if (t >= x0 && t <= x1) ticks.push(t);
    }
  }
  const tickStep = Math.ceil(ticks.length / (mini ? 3 : Math.max(2, Math.floor(W / 80))));
  ticks.filter((_, i) => i % tickStep === 0).forEach((t) => {
    const d = new Date(t);
    const label = spanYears > 2.5 ? String(d.getUTCFullYear())
      : d.getUTCMonth() === 0 ? `${d.getUTCFullYear()}.1` : `${d.getUTCMonth() + 1}월`;
    const tx = svg("text", { x: X(t), y: m.t + H + 18, "text-anchor": "middle" });
    tx.textContent = label;
    root.append(tx);
  });

  // 면 · 선
  const path = (key) => points.map((p, i) => (p[key] == null ? null : [X(xs[i]), Y(p[key])]))
    .reduce((acc, pt) => {
      if (!pt) { acc.pen = "M"; return acc; }
      acc.d += `${acc.pen}${pt[0].toFixed(1)},${pt[1].toFixed(1)}`;
      acc.pen = "L";
      return acc;
    }, { d: "", pen: "M" }).d;
  const valuePath = path("value");
  if (!mini) {
    root.append(svg("path", { class: "area", d: `${valuePath}L${X(x1).toFixed(1)},${Y(Math.max(lo, 0))}L${X(x0).toFixed(1)},${Y(Math.max(lo, 0))}Z` }));
  }
  root.append(svg("path", { class: "line s1", d: valuePath }));
  if (hasMA) root.append(svg("path", { class: "line s2", d: path("ma") }));

  // 메모 점(큰 그래프)
  if (!mini) {
    points.forEach((p, i) => {
      if (p.memo) root.append(svg("circle", { class: "memo-dot", cx: X(xs[i]), cy: Y(p.value), r: 4 }));
    });
  }

  // 직접 표기 — 끝값, 최고점
  const lastP = points[points.length - 1];
  const endLabel = (val, cls, dy = 0) => {
    root.append(svg("circle", { class: `end-dot ${cls}`, cx: X(x1), cy: Y(val), r: 4 }));
    const t = svg("text", { x: X(x1) + 8, y: Y(val) + 4 + dy, class: "label-strong" });
    t.textContent = fmt(val, 1);
    root.append(t);
  };
  endLabel(lastP.value, "s1");
  if (hasMA && lastP.ma != null) {
    const gap = Math.abs(Y(lastP.ma) - Y(lastP.value));
    if (gap > 12) endLabel(lastP.ma, "s2");
  }
  if (!mini) {
    const iMax = points.reduce((b, p, i) => (p.value > points[b].value ? i : b), 0);
    if (iMax !== points.length - 1) {
      const px = X(xs[iMax]);
      const t = svg("text", { x: Math.min(Math.max(px, m.l + 40), m.l + W - 40), y: Y(points[iMax].value) - 8, "text-anchor": "middle", class: "label-strong" });
      t.textContent = `최고 ${fmt(points[iMax].value, 1)} (${points[iMax].date})`;
      root.append(t);
    }
  }

  // 십자선 + 툴팁 — 포인터가 가장 가까운 날짜에 붙는다
  const cross = svg("line", { class: "crosshair", y1: m.t, y2: m.t + H, visibility: "hidden" });
  const hover1 = svg("circle", { class: "end-dot s1", r: 4, visibility: "hidden" });
  const hover2 = svg("circle", { class: "end-dot s2", r: 4, visibility: "hidden" });
  const hit = svg("rect", { class: "hit", x: m.l, y: m.t, width: W, height: H, tabindex: "0",
    "aria-label": "그래프 값 읽기: 방향키로 이동" });
  root.append(cross, hover1, hover2, hit);
  box.append(root);

  const tip = el("div", { class: "tooltip", hidden: true });
  box.append(tip);
  let idx = -1;
  const show = (i) => {
    idx = Math.max(0, Math.min(points.length - 1, i));
    const p = points[idx];
    const cx = X(xs[idx]);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
    hover1.setAttribute("cx", cx); hover1.setAttribute("cy", Y(p.value)); hover1.setAttribute("visibility", "visible");
    if (hasMA && p.ma != null) {
      hover2.setAttribute("cx", cx); hover2.setAttribute("cy", Y(p.ma)); hover2.setAttribute("visibility", "visible");
    } else hover2.setAttribute("visibility", "hidden");
    tip.replaceChildren(
      el("div", { class: "t-date", text: p.date }),
      el("div", { class: "t-row" }, el("i", { style: "background:var(--series-1)" }), el("b", { text: fmt(p.value, 2) }), "값"),
      hasMA ? el("div", { class: "t-row" }, el("i", { style: "background:var(--series-2)" }), el("b", { text: fmt(p.ma, 2) }), opt.maLabel || "이동평균") : null,
      p.memo ? el("div", { class: "t-memo", text: p.memo }) : null,
    );
    tip.hidden = false;
    const scale = box.clientWidth / width;
    const left = cx * scale;
    const tw = tip.offsetWidth;
    tip.style.left = `${left + 12 + tw > box.clientWidth ? left - tw - 12 : left + 12}px`;
    tip.style.top = `${(mini ? 0 : 24) + m.t * scale}px`;
  };
  const hide = () => {
    tip.hidden = true;
    for (const n of [cross, hover1, hover2]) n.setAttribute("visibility", "hidden");
  };
  const nearest = (clientX) => {
    const r = root.getBoundingClientRect();
    const t = x0 + (((clientX - r.left) * (width / r.width) - m.l) / W) * (x1 - x0);
    let best = 0;
    for (let i = 1; i < xs.length; i++) if (Math.abs(xs[i] - t) < Math.abs(xs[best] - t)) best = i;
    return best;
  };
  hit.addEventListener("pointermove", (e) => show(nearest(e.clientX)));
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("focus", () => show(idx < 0 ? points.length - 1 : idx));
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", (e) => {
    const stepKeys = { ArrowLeft: -1, ArrowRight: 1, Home: -1e9, End: 1e9 };
    if (e.key in stepKeys) {
      e.preventDefault();
      show((idx < 0 ? points.length - 1 : idx) + stepKeys[e.key]);
    } else if (e.key === "Escape") hide();
  });
}

// 컨테이너 폭이 바뀌면 다시 그린다
export function autoResize(box, draw) {
  let last = box.clientWidth;
  new ResizeObserver(() => {
    if (Math.abs(box.clientWidth - last) > 4) {
      last = box.clientWidth;
      draw();
    }
  }).observe(box);
}
