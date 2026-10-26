// 시연 페이지: 사진 선택 → 브라우저에서 축소·base64 → 매트릭스와 함께 POST /api/alt_text → 결과 표시.
(function () {
  var MAX_SIDE = 1600;            // 긴 변 기준 축소 (요청 본문 4.5MB 한도 안전)
  var JPEG_QUALITY = 0.86;
  var TIMEOUT_MS = 30000;         // 지연 안내 기준

  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("file");
  var preview = document.getElementById("preview");
  var hint = document.getElementById("drop-hint");
  var fileMeta = document.getElementById("file-meta");
  var clearBtn = document.getElementById("clear");
  var form = document.getElementById("demo-form");
  var submitBtn = document.getElementById("submit");
  var status = document.getElementById("status");
  var alertBox = document.getElementById("alert");
  var result = document.getElementById("result");
  var keyPreview = document.getElementById("key-preview");
  var matrixBox = document.getElementById("matrix");
  var AXES = ["domain", "content_type", "image_kind", "category", "tone", "length", "language"];
  var AXIS_LABEL = { domain: "분야", content_type: "콘텐츠 유형", image_kind: "이미지 유형", category: "카테고리", tone: "톤", length: "길이", language: "언어" };

  var imageB64 = null, imageMime = "image/jpeg";

  // ---- 1) 매트릭스 선택지: GET /api/options ----
  fetch("/api/options").then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (opt) {
    AXES.forEach(function (axis) {
      var sel = document.getElementById("axis-" + axis);
      if (!sel) return;
      sel.innerHTML = "";
      (opt[axis] || []).forEach(function (o) {
        var el = document.createElement("option");
        el.value = o.key; el.textContent = o.label;
        if (opt.defaults && opt.defaults[axis] === o.key) el.selected = true;
        sel.appendChild(el);
      });
    });
    applyPreset();
    updateKey();
  }).catch(function (err) {
    showAlert("매트릭스 선택지를 불러오지 못했습니다(" + err.message + "). 새로고침해 주세요.");
  });

  // ?preset=domain.content_type.image_kind.category.tone (매트릭스 페이지 예시 카드·샘플 버튼)
  function applyPreset(preset) {
    var p = preset || new URLSearchParams(location.search).get("preset");
    if (!p) return;
    var parts = p.split(".");
    ["domain", "content_type", "image_kind", "category", "tone"].forEach(function (axis, i) {
      var sel = document.getElementById("axis-" + axis);
      if (sel && parts[i] && [].some.call(sel.options, function (o) { return o.value === parts[i]; })) sel.value = parts[i];
    });
  }

  function selection() {
    var s = {};
    AXES.forEach(function (axis) { var el = document.getElementById("axis-" + axis); s[axis] = el ? el.value : ""; });
    return s;
  }
  function updateKey() {
    var s = selection();
    keyPreview.textContent = [s.domain, s.content_type, s.image_kind, s.category, s.tone].join(".");
  }
  matrixBox.addEventListener("change", updateKey);

  // ---- 2) 이미지 선택·드롭 → 캔버스 축소 ----
  function pickFile(file) {
    hideAlert();
    if (!file) return;
    if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type)) {
      showAlert("JPEG·PNG·WebP·GIF 이미지만 올릴 수 있습니다.");
      return;
    }
    var img = new Image();
    var url = URL.createObjectURL(file);
    img.onload = function () {
      var w = img.naturalWidth, h = img.naturalHeight;
      var scale = Math.min(1, MAX_SIDE / Math.max(w, h));
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      var dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
      imageB64 = dataUrl.split(",")[1]; imageMime = "image/jpeg";
      preview.src = dataUrl; preview.hidden = false; hint.hidden = true;
      var kb = Math.round(imageB64.length * 0.75 / 1024);
      fileMeta.textContent = file.name + " · 원본 " + w + "×" + h + " → 전송 " + canvas.width + "×" + canvas.height + " (" + kb + "KB)";
      clearBtn.hidden = false;
      URL.revokeObjectURL(url);
    };
    img.onerror = function () { showAlert("이미지를 읽지 못했습니다. 다른 파일로 시도해 주세요."); URL.revokeObjectURL(url); };
    img.src = url;
  }
  fileInput.addEventListener("change", function () { pickFile(fileInput.files[0]); });
  dropzone.addEventListener("click", function (e) { if (e.target !== clearBtn) fileInput.click(); });
  dropzone.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
  ["dragenter", "dragover"].forEach(function (ev) { dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add("is-over"); }); });
  ["dragleave", "drop"].forEach(function (ev) { dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.remove("is-over"); }); });
  dropzone.addEventListener("drop", function (e) { pickFile(e.dataTransfer.files[0]); });
  document.addEventListener("paste", function (e) {
    var item = [].find.call(e.clipboardData.items || [], function (i) { return i.type.indexOf("image/") === 0; });
    if (item) pickFile(item.getAsFile());
  });
  // 샘플 이미지 버튼: 파일을 받아 일반 업로드와 같은 경로로 처리
  document.querySelectorAll(".sample").forEach(function (btn) {
    btn.addEventListener("click", function () {
      fetch(btn.getAttribute("data-src")).then(function (r) { return r.blob(); }).then(function (blob) {
        pickFile(new File([blob], btn.getAttribute("data-src").split("/").pop(), { type: blob.type || "image/jpeg" }));
        applyPreset(btn.getAttribute("data-preset")); updateKey();
      }).catch(function () { showAlert("샘플 이미지를 불러오지 못했습니다."); });
    });
  });
  clearBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    imageB64 = null; preview.hidden = true; preview.src = ""; hint.hidden = false; fileMeta.textContent = ""; clearBtn.hidden = true; fileInput.value = "";
    result.setAttribute("data-show", "false");
  });

  // ---- 3) 생성 요청: POST /api/alt_text (타임아웃·오류 안내) ----
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    hideAlert();
    if (!imageB64) { showAlert("사진을 올려 주세요. 대체텍스트를 만들 이미지가 없습니다."); dropzone.focus(); return; }
    var payload = { image: imageB64, mime: imageMime, matrix: selection(), context: document.getElementById("context").value };
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, TIMEOUT_MS);
    setBusy(true);
    var started = Date.now();
    fetch("/api/alt_text", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, status: r.status, body: body }; }); })
      .then(function (res) {
        if (!res.ok) {
          var msg = (res.body && res.body.message) || ("요청이 실패했습니다 (HTTP " + res.status + ").");
          if (res.status >= 500) msg += " 잠시 후 다시 시도해 주세요.";
          showAlert(msg + " [" + (res.body && res.body.error || res.status) + "]");
          return;
        }
        render(res.body, Date.now() - started);
      })
      .catch(function (err) {
        if (err.name === "AbortError") showAlert("응답이 " + (TIMEOUT_MS / 1000) + "초 안에 오지 않았습니다. 네트워크 상태를 확인하고 잠시 후 다시 시도해 주세요.");
        else showAlert("네트워크 오류로 요청을 보내지 못했습니다(" + err.message + ").");
      })
      .finally(function () { clearTimeout(timer); setBusy(false); });
  });

  function setBusy(busy) {
    submitBtn.disabled = busy;
    status.innerHTML = busy ? '<span class="spinner" aria-hidden="true"></span> AI 가 사진을 읽고 있어요… (보통 3~10초)' : "";
    status.setAttribute("aria-busy", busy ? "true" : "false");
  }

  // ---- 4) 결과 표시 ----
  function render(d, ms) {
    document.getElementById("r-alt").textContent = d.alt_text || "(빈 결과)";
    document.getElementById("r-key").textContent = d.matrix_key;
    document.getElementById("r-time").textContent = (ms / 1000).toFixed(1) + "초 · " + d.model;
    setField("r-long", d.long_description);
    setField("r-text", d.detected_text);
    document.getElementById("r-deco").textContent = d.is_decorative ? "예 — 의미 없는 장식 이미지로 판단 (alt=\"\" 로 두어도 됩니다)" : "아니오";
    var blocks = document.getElementById("r-blocks"); blocks.innerHTML = "";
    (d.blocks || []).forEach(function (b) { var c = document.createElement("span"); c.className = "chip"; c.textContent = b; blocks.appendChild(c); });
    document.getElementById("r-prompt").textContent = d.prompt || "";
    var warn = document.getElementById("r-replaced");
    if (d.replaced && d.replaced.length) { warn.textContent = "알 수 없는 선택값은 기본값으로 대체했습니다: " + d.replaced.join(", "); warn.setAttribute("data-show", "true"); }
    else warn.setAttribute("data-show", "false");
    document.getElementById("r-html").textContent = '<img src="photo.jpg" alt="' + (d.is_decorative ? "" : (d.alt_text || "").replace(/"/g, "&quot;")) + '">';
    result.setAttribute("data-show", "true");
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function setField(id, text) {
    var dd = document.getElementById(id);
    dd.textContent = text || "없음";
    dd.parentElement.style.opacity = text ? 1 : .6;
  }

  // 복사 버튼
  document.getElementById("copy").addEventListener("click", function () {
    var text = document.getElementById("r-alt").textContent;
    var done = document.getElementById("copied");
    navigator.clipboard.writeText(text).then(function () { done.textContent = "복사됨"; setTimeout(function () { done.textContent = ""; }, 1500); })
      .catch(function () { done.textContent = "복사 실패 — 직접 선택해 주세요"; });
  });

  function showAlert(msg) { alertBox.textContent = msg; alertBox.setAttribute("data-show", "true"); alertBox.focus(); }
  function hideAlert() { alertBox.setAttribute("data-show", "false"); }
})();
