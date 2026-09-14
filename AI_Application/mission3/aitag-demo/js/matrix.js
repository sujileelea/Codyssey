// 매트릭스 페이지: GET /api/options 로 축별 선택지를 표로 그리고, 예시 조합 카드는 시연 페이지로 연결한다.
(function () {
  var table = document.getElementById("axis-rows");
  var LABEL = { domain: "분야 (domain)", content_type: "콘텐츠 유형 (content_type)", image_kind: "이미지 유형 (image_kind)", category: "카테고리 (category)", tone: "톤 (tone)", length: "길이 (length)", language: "언어 (language)" };
  fetch("/api/options").then(function (r) { return r.json(); }).then(function (opt) {
    table.innerHTML = "";
    Object.keys(LABEL).forEach(function (axis) {
      var tr = document.createElement("tr");
      var th = document.createElement("th"); th.scope = "row"; th.textContent = LABEL[axis];
      var td = document.createElement("td");
      td.innerHTML = (opt[axis] || []).map(function (o) { return "<code>" + o.key + "</code> " + o.label; }).join(" · ");
      tr.appendChild(th); tr.appendChild(td); table.appendChild(tr);
    });
  }).catch(function () { table.innerHTML = '<tr><td colspan="2">선택지를 불러오지 못했습니다. 새로고침해 주세요.</td></tr>'; });

  document.querySelectorAll(".examples .card").forEach(function (card) {
    card.addEventListener("click", function () { location.href = "demo.html?preset=" + card.getAttribute("data-preset"); });
    card.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); card.click(); } });
  });
})();
