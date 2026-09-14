// 모든 페이지 공통: 다크 모드 토글, 모바일 내비, 현재 페이지 표시.
(function () {
  var root = document.documentElement;

  // 다크 모드 — 저장값 > 시스템 설정 순으로 적용 (보너스: UX)
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var btn = document.querySelector(".theme-toggle");
    if (btn) {
      btn.textContent = theme === "dark" ? "☀️" : "🌙";
      btn.setAttribute("aria-label", theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환");
    }
  }
  var saved = null;
  try { saved = localStorage.getItem("aitag-theme"); } catch (e) {}
  var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));

  document.addEventListener("click", function (e) {
    var t = e.target.closest(".theme-toggle");
    if (!t) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("aitag-theme", next); } catch (err) {}
  });

  // 모바일 내비 열기/닫기
  var navToggle = document.querySelector(".nav-toggle");
  var nav = document.querySelector(".nav");
  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var open = nav.getAttribute("data-open") === "true";
      nav.setAttribute("data-open", open ? "false" : "true");
      navToggle.setAttribute("aria-expanded", open ? "false" : "true");
    });
  }

  // 현재 페이지 링크 강조
  var here = location.pathname.replace(/\/index\.html$/, "/");
  document.querySelectorAll(".nav a").forEach(function (a) {
    var href = a.getAttribute("href").replace(/\/index\.html$/, "/");
    var match = href === "/" ? (here === "/" || here === "") : here.endsWith(href.replace(/^\.\//, ""));
    if (match) a.setAttribute("aria-current", "page");
  });
})();
