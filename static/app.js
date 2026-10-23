(function () {
  "use strict";

  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("fileInput");
  var chooseBtn = document.getElementById("chooseBtn");
  var targetInput = document.getElementById("targetMb");
  var resultsEl = document.getElementById("results");
  var modal = document.getElementById("compareModal");
  var modalBody = document.getElementById("compareBody");
  var modalTitle = document.getElementById("compareTitle");

  var queue = Promise.resolve();
  var dragDepth = 0;
  var lastFocus = null;
  var compareState = null;

  var ACCEPT_EXT = [".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif", ".pdf"];
  var SSIM_HELP = "SSIM gần 1.0 = gần giống bản gốc; chỉ là chỉ số tham khảo, hãy tự xem ảnh so sánh.";

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtSize(bytes) {
    if (typeof bytes !== "number" || !isFinite(bytes)) return "—";
    if (bytes < 1024 * 1024) {
      return (bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0) + " KB";
    }
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  }

  function extOf(name) {
    var i = String(name || "").lastIndexOf(".");
    return i >= 0 ? String(name).slice(i).toLowerCase() : "";
  }

  function addFiles(files) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;
    queue = queue.then(function () { return runBatch(list); });
  }

  async function runBatch(files) {
    for (var i = 0; i < files.length; i++) {
      await processOne(files[i]);
    }
  }

  function createCard(file) {
    var card = document.createElement("article");
    card.className = "card";
    card.innerHTML =
      '<div class="card-top">' +
        '<div>' +
          '<h3 class="file-name">' + esc(file.name) + '</h3>' +
          '<p class="file-meta">' + esc(fmtSize(file.size)) + ' · ' + esc(extOf(file.name).replace(".", "").toUpperCase() || "TỆP") + '</p>' +
        '</div>' +
        '<span class="pill">Đang chờ</span>' +
      '</div>' +
      '<div class="working"><span class="spinner" aria-hidden="true"></span><span>Đang nén...</span></div>' +
      '<div class="progress" aria-hidden="true"></div>' +
      '<div class="result" hidden></div>';
    resultsEl.appendChild(card);
    return card;
  }

  function setError(card, message) {
    var pill = card.querySelector(".pill");
    pill.textContent = "Lỗi";
    pill.className = "pill error";
    var working = card.querySelector(".working");
    if (working) working.remove();
    var progress = card.querySelector(".progress");
    if (progress) progress.remove();
    var result = card.querySelector(".result");
    result.hidden = false;
    result.innerHTML = '<div class="error-box">' + esc(message) + '</div>';
  }

  async function processOne(file) {
    var card = createCard(file);
    var target = parseFloat(targetInput.value);
    if (!isFinite(target) || target <= 0) target = 5;

    var form = new FormData();
    form.append("file", file);
    form.append("target_mb", String(target));

    try {
      var response = await fetch("/api/compress", { method: "POST", body: form });
      var data = null;
      try { data = await response.json(); } catch (e) { data = null; }
      if (!response.ok || !data || data.error) {
        throw new Error((data && data.error) || "Máy chủ không trả về kết quả hợp lệ.");
      }
      renderResult(card, data, file);
    } catch (err) {
      setError(card, err && err.message ? err.message : "Không xử lý được file này.");
    }
  }

  function subsamplingText(v) {
    if (v === 0) return "4:4:4";
    if (v === 1) return "4:2:2";
    if (v === 2) return "4:2:0";
    return "";
  }

  function qualityText(d) {
    if (d.status === "already_small") return "Không đổi";
    if (d.kind === "image") {
      var q = "chất lượng " + (d.quality == null ? "—" : d.quality);
      var sub = d.format === "JPEG" ? subsamplingText(d.subsampling) : "";
      return d.format + " · " + q + (sub ? " · " + sub : "");
    }
    if (d.quality == null) return "Không nén thêm ảnh";
    return "JPEG q" + d.quality + " · " + (d.dpi == null ? "—" : d.dpi + " DPI");
  }

  function resolutionText(d) {
    if (d.kind === "image") {
      return d.original_width + " × " + d.original_height + " → " + d.output_width + " × " + d.output_height;
    }
    var dpi = d.dpi == null ? "giữ nguyên ảnh" : d.dpi + " DPI";
    return d.page_count + " trang · " + dpi;
  }

  function statusKind(d) {
    if (d.status === "target_not_met") return "warn";
    if (d.status === "already_small") return "notice";
    if (d.kind === "pdf" && d.text_identical === false) return "warn";
    return "ok";
  }

  function statusMark(kind) {
    if (kind === "warn") return "!";
    if (kind === "notice") return "i";
    return "✓";
  }

  function renderResult(card, d, file) {
    var working = card.querySelector(".working");
    if (working) working.remove();
    var progress = card.querySelector(".progress");
    if (progress) progress.remove();

    var kind = statusKind(d);
    var pill = card.querySelector(".pill");
    pill.textContent = d.status === "already_small" ? "Giữ nguyên" : (d.status === "target_not_met" ? "Chưa đạt" : "Hoàn tất");
    pill.className = "pill " + kind;

    var reduce = (typeof d.reduction_percent === "number") ? d.reduction_percent : 0;
    var reduceText = d.status === "already_small"
      ? "0.0%"
      : (reduce >= 0 ? "−" + reduce.toFixed(1) + "%" : "+" + Math.abs(reduce).toFixed(1) + "%");

    var warnings = Array.isArray(d.warnings) ? d.warnings : [];
    var warningsHtml = warnings.length
      ? '<ul class="warnings">' + warnings.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") + "</ul>"
      : "";
    var notes = Array.isArray(d.notes) ? d.notes : [];
    var notesHtml = notes.length
      ? '<ul class="notes">' + notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>"
      : "";

    var compareBtn = '<button class="btn ghost" type="button" data-compare>So sánh</button>';
    var result = card.querySelector(".result");
    result.hidden = false;
    result.innerHTML =
      '<div class="stats">' +
        '<div class="stat"><div class="k">Trước</div><div class="v">' + esc(fmtSize(d.original_bytes)) + '</div></div>' +
        '<div class="stat"><div class="k">Sau</div><div class="v">' + esc(fmtSize(d.output_bytes)) + '</div></div>' +
        '<div class="stat"><div class="k">Giảm</div><div class="v">' + esc(reduceText) + '</div></div>' +
        '<div class="stat"><div class="k">Độ phân giải</div><div class="v">' + esc(resolutionText(d)) + '</div></div>' +
        '<div class="stat"><div class="k">Định dạng / chất lượng</div><div class="v">' + esc(qualityText(d)) + '</div></div>' +
        '<div class="stat"><div class="k">SSIM <span class="help" title="' + esc(SSIM_HELP) + '">?</span></div><div class="v">' + esc(Number(d.ssim).toFixed(4)) + '</div></div>' +
      '</div>' +
      '<div class="status-line ' + kind + '"><span class="mark" aria-hidden="true">' + statusMark(kind) + '</span><span>' + esc(d.status_message) + '</span></div>' +
      warningsHtml +
      notesHtml +
      '<div class="card-actions">' +
        '<a class="btn primary" href="/api/download/' + encodeURIComponent(d.job_id) + '">Tải về</a>' +
        (d.kind === "image" || d.kind === "pdf" ? compareBtn : "") +
        '<span class="out-name">' + esc(d.output_filename) + '</span>' +
      '</div>';

    var btn = result.querySelector("[data-compare]");
    if (btn) {
      btn.addEventListener("click", function () {
        openCompare(d, file ? file.name : d.filename);
      });
    }
  }

  /* -------------------- Compare modal -------------------- */

  function openCompare(d, filename) {
    compareState = {
      d: d,
      filename: filename,
      page: 0
    };
    lastFocus = document.activeElement;
    modalTitle.textContent = "So sánh · " + filename;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    renderCompare();
    var closeBtn = modal.querySelector(".icon-btn");
    if (closeBtn) closeBtn.focus();
  }

  function closeCompare() {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    modalBody.innerHTML = "";
    compareState = null;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function previewUrl(which, page) {
    var base = "/api/preview/" + encodeURIComponent(compareState.d.job_id) + "/" + which;
    if (typeof page === "number") base += "?page=" + page;
    return base;
  }

  function imgFigure(label, cls, which, page) {
    return '<figure>' +
      '<figcaption class="' + cls + '">' + esc(label) + '</figcaption>' +
      '<div class="img-shell">' +
        '<span class="loading">Đang tạo ảnh so sánh...</span>' +
        '<img alt="' + esc(label) + '" src="' + previewUrl(which, page) + '">' +
      '</div>' +
    '</figure>';
  }

  function wireImages(root) {
    var imgs = root.querySelectorAll(".img-shell img");
    Array.prototype.forEach.call(imgs, function (img) {
      var shell = img.parentElement;
      function ready() { shell.classList.add("ready"); }
      function failed() {
        shell.classList.add("error");
        var loading = shell.querySelector(".loading");
        if (loading) loading.textContent = "Không tạo được ảnh xem trước.";
      }
      if (img.complete) {
        if (img.naturalWidth) ready(); else failed();
      } else {
        img.addEventListener("load", ready);
        img.addEventListener("error", failed);
      }
    });
  }

  function renderCompare() {
    if (!compareState) return;
    var d = compareState.d;
    var html = "";

    if (d.kind === "image") {
      html +=
        '<section class="compare-block">' +
          '<h3>Toàn bộ ảnh</h3>' +
          '<div class="pair">' +
            imgFigure("Bản gốc", "", "orig_full", null) +
            imgFigure("Sau nén", "out", "out_full", null) +
          '</div>' +
        '</section>' +
        '<section class="compare-block">' +
          '<h3>Cắt 100% ở giữa ảnh</h3>' +
          '<div class="pair">' +
            imgFigure("Bản gốc", "", "orig_crop", null) +
            imgFigure("Sau nén", "out", "out_crop", null) +
          '</div>' +
        '</section>';
    } else {
      var total = Number(d.page_count) || 1;
      var page = Math.max(0, Math.min(compareState.page, total - 1));
      compareState.page = page;
      html +=
        '<div class="pdf-nav">' +
          '<button class="btn ghost" type="button" data-prev aria-label="Trang trước"' + (page <= 0 ? " disabled" : "") + '>← Trước</button>' +
          '<span>Trang ' + (page + 1) + ' / ' + total + '</span>' +
          '<button class="btn ghost" type="button" data-next aria-label="Trang sau"' + (page >= total - 1 ? " disabled" : "") + '>Sau →</button>' +
        '</div>' +
        '<div class="pair">' +
          imgFigure("Bản gốc · trang " + (page + 1), "", "orig_page", page) +
          imgFigure("Sau nén · trang " + (page + 1), "out", "out_page", page) +
        '</div>';
    }

    modalBody.innerHTML = html;
    wireImages(modalBody);

    var prev = modalBody.querySelector("[data-prev]");
    var next = modalBody.querySelector("[data-next]");
    if (prev) prev.addEventListener("click", function () {
      compareState.page = Math.max(0, compareState.page - 1);
      renderCompare();
    });
    if (next) next.addEventListener("click", function () {
      var total = Number(compareState.d.page_count) || 1;
      compareState.page = Math.min(total - 1, compareState.page + 1);
      renderCompare();
    });
  }

  /* -------------------- Events -------------------- */

  function openPicker() { fileInput.click(); }

  chooseBtn.addEventListener("click", openPicker);
  dropzone.addEventListener("click", openPicker);
  dropzone.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPicker();
    }
  });

  fileInput.addEventListener("change", function () {
    addFiles(fileInput.files);
    fileInput.value = "";
  });

  ["dragenter", "dragover", "dragleave", "drop"].forEach(function (name) {
    document.addEventListener(name, function (e) { e.preventDefault(); });
  });

  dropzone.addEventListener("dragenter", function () {
    dragDepth++;
    dropzone.classList.add("dragging");
  });

  dropzone.addEventListener("dragover", function (e) {
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    dropzone.classList.add("dragging");
  });

  dropzone.addEventListener("dragleave", function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) dropzone.classList.remove("dragging");
  });

  dropzone.addEventListener("drop", function (e) {
    dragDepth = 0;
    dropzone.classList.remove("dragging");
    if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
  });

  modal.addEventListener("click", function (e) {
    var target = e.target;
    if (target && target.hasAttribute && target.hasAttribute("data-close")) closeCompare();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeCompare();
  });
})();
