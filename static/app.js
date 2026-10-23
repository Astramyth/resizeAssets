(function () {
  "use strict";

  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("fileInput");
  var chooseBtn = document.getElementById("chooseBtn");
  var targetInput = document.getElementById("targetMb");
  var resultsEl = document.getElementById("results");
  var emptyState = document.getElementById("emptyState");
  var pageDrop = document.getElementById("pageDrop");
  var toastEl = document.getElementById("toast");
  var modal = document.getElementById("compareModal");
  var modalBody = document.getElementById("compareBody");
  var modalTitle = document.getElementById("compareTitle");

  var queue = Promise.resolve();
  var creationChain = Promise.resolve();
  var currentBatch = null;
  var olderWrap = null;
  var olderToggle = null;
  var olderList = null;
  var olderTitle = null;
  var olderCount = 0;
  var batchSeq = 0;
  var dragDepth = 0;
  var lastFocus = null;
  var compareState = null;
  var toastTimer = null;

  var ACCEPT_EXT = [".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif", ".pdf"];
  var SSIM_HELP = "SSIM gần 1.0 = gần giống bản gốc; chỉ là chỉ số tham khảo, hãy tự xem ảnh so sánh.";

  var ROW_STATUS = {
    pending: { label: "Đang chờ", cls: "pending", icon: "clock" },
    uploading: { label: "Đang tải lên", cls: "pending", icon: "upload" },
    compressing: { label: "Đang nén", cls: "pending", icon: "spinner" },
    done: { label: "Hoàn tất", cls: "ok", icon: "check" },
    unchanged: { label: "Giữ nguyên", cls: "notice", icon: "info" },
    warn: { label: "Chưa đạt mục tiêu", cls: "warn", icon: "warn" },
    error: { label: "Lỗi", cls: "error", icon: "error" }
  };

  /* -------------------- Helpers -------------------- */

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

  function fmtSummarySize(bytes) {
    if (typeof bytes !== "number" || !isFinite(bytes)) return "—";
    var mb = bytes / (1024 * 1024);
    if (mb >= 10) return Math.round(mb) + " MB";
    if (mb >= 1) {
      var rounded = (Math.round(mb * 10) / 10).toFixed(1).replace(/\.0$/, "");
      return rounded + " MB";
    }
    return fmtSize(bytes);
  }

  function extOf(name) {
    var i = String(name || "").lastIndexOf(".");
    return i >= 0 ? String(name).slice(i).toLowerCase() : "";
  }

  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function timeLabel(date) {
    return pad2(date.getHours()) + ":" + pad2(date.getMinutes());
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function canAnimate() {
    return !reducedMotion() && !!window.Motion && typeof window.Motion.animate === "function";
  }

  function anim(el, keyframes, options) {
    if (!canAnimate() || !el) return Promise.resolve();
    var ms = options && typeof options.duration === "number" ? options.duration * 1000 : 350;
    var fallback = new Promise(function (resolve) {
      window.setTimeout(resolve, ms + 80);
    });
    try {
      var controls = window.Motion.animate(el, keyframes, options || {});
      if (controls && controls.finished && typeof controls.finished.then === "function") {
        return Promise.race([controls.finished.catch(function () {}), fallback]);
      }
    } catch (err) {
      return fallback;
    }
    return fallback;
  }

  function svgIcon(name) {
    var paths = {
      check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/>',
      info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
      warn: '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
      error: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/>',
      clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
      upload: '<path d="M12 16V4m0 0 4 4m-4-4-4 4"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
      image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="m4 18 5-5 3 3 3-3 5 5"/>',
      pdf: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4"/><path d="M9 13h1.5a1.5 1.5 0 0 1 0 3H9v-3Zm0 3v2M14 13v5M14 15h2"/>'
    };
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (paths[name] || paths.clock) + "</svg>";
  }

  function kindOf(name) {
    return extOf(name) === ".pdf" ? "pdf" : "image";
  }

  function filenameFromHeader(header) {
    if (!header) return "";
    var match = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (match) {
      try {
        return decodeURIComponent(match[1].replace(/^"|"$/g, ""));
      } catch (err) {
        return match[1];
      }
    }
    match = /filename="?([^";]+)"?/i.exec(header);
    return match ? match[1].trim() : "";
  }

  function saveBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename || "da-nen";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function showToast(message) {
    if (!toastEl) return;
    if (toastTimer) window.clearTimeout(toastTimer);
    toastEl.textContent = message;
    toastEl.hidden = false;
    anim(toastEl, { opacity: [0, 1], y: [12, 0] }, { duration: 0.2, ease: "easeOut" });
    toastTimer = window.setTimeout(function () {
      var done = anim(toastEl, { opacity: [1, 0], y: [0, 8] }, { duration: 0.15, ease: "easeIn" });
      done.then(function () {
        toastEl.hidden = true;
        toastEl.style.opacity = "";
        toastEl.style.transform = "";
      });
    }, 4000);
  }

  /* -------------------- Batch creation -------------------- */

  function addFiles(files) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return;

    var supported = [];
    var skipped = [];
    list.forEach(function (file) {
      if (ACCEPT_EXT.indexOf(extOf(file.name)) !== -1) supported.push(file);
      else skipped.push(file.name);
    });

    creationChain = creationChain
      .then(function () { createBatch(supported, skipped); })
      .catch(function () { createBatch(supported, skipped); });
  }

  function createBatch(files, skipped) {
    batchSeq += 1;
    var batch = {
      id: batchSeq,
      files: files,
      total: files.length,
      done: 0,
      success: 0,
      errors: 0,
      warningCount: 0,
      results: [],
      rows: [],
      finished: false,
      zipBusy: false,
      zipToastShown: false,
      singleBusy: false
    };

    var article = document.createElement("article");
    article.className = "batch";
    article.setAttribute("data-batch", String(batch.id));

    var skippedHtml = "";
    if (skipped.length) {
      skippedHtml =
        '<p class="batch-skipped" data-skipped>Bỏ qua ' + skipped.length +
        ' file không hỗ trợ: ' + skipped.map(esc).join(", ") + "</p>";
    }

    article.innerHTML =
      '<header class="batch-head">' +
        '<div class="batch-title-row">' +
          '<h3 class="batch-title">Lần nén lúc ' + timeLabel(new Date()) + " · " + files.length + " file</h3>" +
          '<span class="batch-state" data-state>Đang chờ</span>' +
        "</div>" +
        '<div class="batch-progress" data-progress role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-valuetext="Đang chờ nén">' +
          '<div class="batch-bar" aria-hidden="true"><span data-bar></span></div>' +
          '<p class="batch-progress-text" data-progress-text>Đang chờ · 0/' + files.length + " file</p>" +
        "</div>" +
        '<p class="batch-summary" data-summary hidden></p>' +
        skippedHtml +
        '<p class="batch-error" data-batch-error hidden></p>' +
        '<div class="batch-actions" data-actions hidden></div>' +
        '<p class="sr-only" data-live aria-live="polite"></p>' +
      "</header>" +
      '<ul class="file-rows" id="rows-' + batch.id + '" data-rows></ul>';

    batch.el = article;
    batch.rowsEl = article.querySelector("[data-rows]");
    batch.progressEl = article.querySelector("[data-progress]");
    batch.barEl = article.querySelector("[data-bar]");
    batch.progressText = article.querySelector("[data-progress-text]");
    batch.summaryEl = article.querySelector("[data-summary]");
    batch.errorEl = article.querySelector("[data-batch-error]");
    batch.actionsEl = article.querySelector("[data-actions]");
    batch.stateEl = article.querySelector("[data-state]");
    batch.liveEl = article.querySelector("[data-live]");

    batch.rows = files.map(function (file, index) {
      var detailId = "detail-" + batch.id + "-" + index;
      var item = document.createElement("li");
      item.className = "file-row";
      item.innerHTML =
        '<div class="row-main">' +
          '<span class="file-icon ' + kindOf(file.name) + '" aria-hidden="true">' + svgIcon(kindOf(file.name)) + "</span>" +
          '<div class="row-info">' +
            '<p class="row-name" title="' + esc(file.name) + '">' + esc(file.name) + "</p>" +
            '<p class="row-size" data-size>' + esc(fmtSize(file.size)) + "</p>" +
            '<p class="row-error" data-row-error hidden></p>' +
          "</div>" +
          '<span class="row-status pending" data-status>' + svgIcon("clock") +
            '<span data-status-text>Đang chờ</span></span>' +
          '<button class="btn ghost row-toggle" type="button" aria-expanded="false" aria-controls="' + detailId + '" data-toggle>Chi tiết</button>' +
        "</div>" +
        '<div class="row-detail" id="' + detailId + '" hidden></div>';

      var entry = {
        file: file,
        row: item,
        detail: item.querySelector(".row-detail"),
        statusEl: item.querySelector("[data-status]"),
        sizeEl: item.querySelector("[data-size]"),
        errorEl: item.querySelector("[data-row-error]"),
        toggleEl: item.querySelector("[data-toggle]")
      };

      entry.toggleEl.addEventListener("click", function () {
        var expanded = entry.toggleEl.getAttribute("aria-expanded") === "true";
        entry.toggleEl.setAttribute("aria-expanded", String(!expanded));
        entry.toggleEl.textContent = expanded ? "Chi tiết" : "Ẩn chi tiết";
        entry.detail.hidden = expanded;
      });

      batch.rowsEl.appendChild(item);
      return entry;
    });

    if (emptyState) emptyState.hidden = true;

    // Queued behind a batch that is still running/waiting: stay visible below it
    // until the queue reaches us. The older batch is demoted at that point.
    if (resultsEl.querySelector(".batch:not(.is-older)")) {
      batch.progressText.textContent = "Sẽ bắt đầu khi lần nén trước xong";
      batch.progressEl.setAttribute("aria-valuetext", "Sẽ bắt đầu khi lần nén trước xong");
    }

    if (olderWrap) resultsEl.insertBefore(article, olderWrap);
    else resultsEl.appendChild(article);

    anim(article, { opacity: [0, 1], y: [12, 0] }, { type: "spring", stiffness: 420, damping: 34, mass: 0.8 });
    batch.rows.forEach(function (entry, index) {
      anim(entry.row, { opacity: [0, 1], y: [8, 0] }, {
        type: "spring",
        stiffness: 420,
        damping: 34,
        mass: 0.8,
        delay: index * 0.04
      });
    });

    queue = queue
      .then(function () { return runBatch(batch); })
      .catch(function (err) {
        setBatchState(batch, "Lỗi");
        showBatchError(batch, (err && err.message) || "Không xử lý được lần nén này.", function () {});
      });
  }

  function setBatchState(batch, text, cls) {
    batch.stateEl.textContent = text;
    batch.stateEl.className = "batch-state" + (cls ? " " + cls : "");
  }

  function setBatchProgress(batch, done, fraction, name, verb) {
    var total = batch.total;
    var overall = total ? Math.min(1, (done + fraction) / total) : 0;
    batch.barEl.style.transform = "scaleX(" + overall + ")";
    var percent = Math.round(overall * 100);
    batch.progressEl.setAttribute("aria-valuenow", String(percent));
    batch.progressEl.setAttribute("aria-valuetext", done + "/" + total + " file đã xong");

    var text;
    if (!verb) {
      text = "Đã xong " + done + "/" + total + " file";
    } else {
      var current = total ? Math.min(total, done + 1) : 0;
      text = verb + " " + current + "/" + total + (name ? " · " + name : "");
    }
    batch.progressText.textContent = text;
  }

  function setRowStatus(entry, state, message) {
    var meta = ROW_STATUS[state] || ROW_STATUS.pending;
    entry.statusEl.className = "row-status " + meta.cls;
    entry.statusEl.innerHTML =
      (state === "compressing"
        ? '<span class="spinner" aria-hidden="true"></span>'
        : svgIcon(meta.icon)) +
      '<span data-status-text>' + esc(meta.label) + "</span>";

    if (message) {
      entry.errorEl.hidden = false;
      entry.errorEl.textContent = message;
    } else {
      entry.errorEl.hidden = true;
      entry.errorEl.textContent = "";
    }

    if (state === "done" || state === "unchanged") {
      var icon = entry.statusEl.querySelector("svg");
      if (icon) anim(icon, { scale: [0.8, 1] }, { type: "spring", stiffness: 540, damping: 26 });
    }
  }

  function setRowSize(entry, data) {
    var reduction = typeof data.reduction_percent === "number" ? data.reduction_percent : 0;
    var change = reduction >= 0 ? "giảm " : "tăng ";
    entry.sizeEl.textContent =
      fmtSize(data.original_bytes) + " → " + fmtSize(data.output_bytes) +
      " · " + change + Math.abs(reduction).toFixed(1) + "%";
  }

  async function runBatch(batch) {
    // A newer batch only starts once the previous one is done; that is the moment
    // the previous batch moves into "Các lần nén trước".
    await demoteCurrent();
    currentBatch = batch;

    window.requestAnimationFrame(function () {
      try {
        batch.el.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
      } catch (err) {
        batch.el.scrollIntoView();
      }
    });

    if (!batch.total) {
      finishBatch(batch);
      return;
    }
    setBatchState(batch, "Đang nén", "running");
    setBatchProgress(batch, 0, 0, batch.files[0].name, "Đang nén");

    for (var i = 0; i < batch.files.length; i++) {
      await processOne(batch, batch.rows[i], i);
    }
    finishBatch(batch);
  }

  function uploadWithProgress(form, onProgress, onUploaded) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/compress");
      xhr.responseType = "text";

      xhr.upload.onprogress = function (event) {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.min(1, event.loaded / event.total));
        }
      };
      xhr.upload.onload = function () {
        if (onUploaded) onUploaded();
      };
      xhr.onload = function () {
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (err) { data = null; }
        if (xhr.status >= 200 && xhr.status < 300 && data && !data.error) {
          resolve(data);
        } else {
          reject(new Error((data && data.error) || "Máy chủ không trả về kết quả hợp lệ."));
        }
      };
      xhr.onerror = function () {
        reject(new Error("Không kết nối được máy chủ. Hãy thử lại."));
      };
      xhr.send(form);
    });
  }

  async function processOne(batch, entry, index) {
    var file = entry.file;
    var target = parseFloat(targetInput.value);
    if (!isFinite(target) || target <= 0) target = 5;

    var form = new FormData();
    form.append("file", file);
    form.append("target_mb", String(target));

    var failed = false;
    setRowStatus(entry, "uploading");
    setBatchProgress(batch, index, 0, file.name, "Đang tải lên");

    try {
      var data = await uploadWithProgress(
        form,
        function (fraction) {
          setBatchProgress(batch, index, fraction, file.name, "Đang tải lên");
        },
        function () {
          setRowStatus(entry, "compressing");
          setBatchProgress(batch, index, 1, file.name, "Đang nén");
        }
      );

      batch.results.push(data);
      batch.success += 1;
      if (hasWarning(data)) batch.warningCount += 1;

      var state = data.status === "already_small"
        ? "unchanged"
        : (data.status === "target_not_met" ? "warn" : "done");
      setRowStatus(entry, state);
      setRowSize(entry, data);
      renderDetails(entry, data, file);
    } catch (err) {
      failed = true;
      batch.errors += 1;
      var message = (err && err.message) ? err.message : "Không xử lý được file này.";
      setRowStatus(entry, "error", message);
      entry.detail.innerHTML = '<div class="error-box">' + esc(message) + "</div>";
    }

    batch.done += 1;
    setBatchProgress(batch, batch.done, 0, null, null);
    batch.liveEl.textContent =
      "Đã xong " + batch.done + "/" + batch.total + " file: " + file.name + (failed ? " (lỗi)" : "");
  }

  function hasWarning(data) {
    return (Array.isArray(data.warnings) && data.warnings.length > 0) ||
      data.status === "target_not_met" ||
      (data.kind === "pdf" && data.text_identical === false);
  }

  function finishBatch(batch) {
    batch.finished = true;
    setBatchState(batch, "Hoàn tất", "done");
    batch.barEl.style.transform = "scaleX(1)";
    batch.progressEl.setAttribute("aria-valuenow", "100");
    batch.progressEl.setAttribute("aria-valuetext", "Đã hoàn tất " + batch.done + "/" + batch.total + " file");
    batch.progressText.textContent = batch.total
      ? "Đã xong " + batch.total + "/" + batch.total + " file"
      : "Không có file nào được nén";

    var summary = buildSummary(batch);
    batch.summaryEl.textContent = summary;
    batch.summaryEl.hidden = false;
    batch.liveEl.textContent = summary;

    if (batch.success >= 2) {
      showZipButton(batch);
      packZip(batch, true);
    } else if (batch.success === 1) {
      showSingleButton(batch);
      downloadSingle(batch, true);
    }
  }

  function buildSummary(batch) {
    var text = "Đã nén " + batch.success + "/" + batch.total + " file";
    if (batch.success > 0) {
      var original = 0;
      var output = 0;
      batch.results.forEach(function (data) {
        original += Number(data.original_bytes) || 0;
        output += Number(data.output_bytes) || 0;
      });
      var percent = original > 0 ? Math.round((1 - output / original) * 100) : 0;
      text += " · " + fmtSummarySize(original) + " → " + fmtSummarySize(output) +
        " (" + (percent >= 0 ? "giảm " : "tăng ") + Math.abs(percent) + "%)";
    }
    var extras = [];
    if (batch.warningCount) extras.push(batch.warningCount + " cảnh báo");
    if (batch.errors) extras.push(batch.errors + " file lỗi");
    if (extras.length) text += " · " + extras.join(" · ");
    return text;
  }

  /* -------------------- ZIP / single download -------------------- */

  function ensureActions(batch) {
    batch.actionsEl.hidden = false;
    if (!batch.primaryBtn) {
      batch.primaryBtn = document.createElement("button");
      batch.primaryBtn.type = "button";
      batch.primaryBtn.className = "btn primary";
      batch.actionsEl.appendChild(batch.primaryBtn);
    }
    return batch.primaryBtn;
  }

  function showBatchError(batch, message, retry) {
    batch.errorEl.hidden = false;
    batch.errorEl.innerHTML =
      "<span>" + esc(message) + "</span>" +
      '<button class="btn ghost" type="button" data-retry>Thử lại</button>';
    var retryBtn = batch.errorEl.querySelector("[data-retry]");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        if (batch.zipBusy || batch.singleBusy) return;
        retry();
      });
    }
  }

  function showZipButton(batch) {
    var btn = ensureActions(batch);
    btn.disabled = false;
    btn.textContent = "Đang đóng gói ZIP...";
  }

  function packZip(batch, automatic) {
    if (batch.zipBusy || !batch.results.length) return;
    var jobIds = batch.results.map(function (data) { return data.job_id; });
    var btn = ensureActions(batch);

    batch.zipBusy = true;
    batch.errorEl.hidden = true;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" aria-hidden="true"></span><span>Đang đóng gói ZIP...</span>';

    fetch("/api/zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_ids: jobIds })
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json()
            .catch(function () { return null; })
            .then(function (data) {
              throw new Error((data && data.error) || "Không đóng gói được file ZIP.");
            });
        }
        var filename = filenameFromHeader(response.headers.get("Content-Disposition")) || "da-nen.zip";
        return response.blob().then(function (blob) {
          return { blob: blob, filename: filename };
        });
      })
      .then(function (result) {
        batch.zipBusy = false;
        saveBlob(result.blob, result.filename);
        btn.disabled = false;
        btn.textContent = "Tải lại file ZIP (" + jobIds.length + " file)";
        btn.onclick = function () {
          if (!batch.zipBusy) packZip(batch, true);
        };
        if (!batch.zipToastShown) {
          batch.zipToastShown = true;
          showToast("Đã đóng gói " + jobIds.length + " file thành ZIP và bắt đầu tải về");
        }
      })
      .catch(function (err) {
        batch.zipBusy = false;
        btn.disabled = false;
        btn.textContent = "Thử lại đóng gói ZIP";
        btn.onclick = function () {
          if (!batch.zipBusy) packZip(batch, true);
        };
        showBatchError(batch, (err && err.message) || "Không đóng gói được file ZIP.", function () {
          packZip(batch, true);
        });
      });
  }

  function showSingleButton(batch) {
    var btn = ensureActions(batch);
    btn.disabled = false;
    btn.textContent = "Tải về";
    btn.onclick = function () {
      if (!batch.singleBusy) downloadSingle(batch, true);
    };
  }

  function downloadSingle(batch, automatic) {
    var data = batch.results[0];
    if (!data || batch.singleBusy) return;
    var btn = ensureActions(batch);

    batch.singleBusy = true;
    batch.errorEl.hidden = true;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" aria-hidden="true"></span><span>Đang tải về...</span>';

    fetch("/api/download/" + encodeURIComponent(data.job_id))
      .then(function (response) {
        if (!response.ok) {
          return response.json()
            .catch(function () { return null; })
            .then(function (body) {
              throw new Error((body && body.error) || "Không tải được file.");
            });
        }
        var filename = filenameFromHeader(response.headers.get("Content-Disposition")) || data.output_filename;
        return response.blob().then(function (blob) {
          return { blob: blob, filename: filename };
        });
      })
      .then(function (result) {
        batch.singleBusy = false;
        saveBlob(result.blob, result.filename);
        btn.disabled = false;
        btn.textContent = "Tải về";
        btn.onclick = function () {
          if (!batch.singleBusy) downloadSingle(batch, true);
        };
      })
      .catch(function (err) {
        batch.singleBusy = false;
        btn.disabled = false;
        btn.textContent = "Thử lại tải về";
        btn.onclick = function () {
          if (!batch.singleBusy) downloadSingle(batch, true);
        };
        showBatchError(batch, (err && err.message) || "Không tải được file.", function () {
          downloadSingle(batch, true);
        });
      });
  }

  /* -------------------- Older batches -------------------- */

  function ensureOlderWrap() {
    if (olderWrap) return;
    olderWrap = document.createElement("section");
    olderWrap.className = "older";
    olderWrap.innerHTML =
      '<button class="older-toggle" type="button" aria-expanded="false">' +
        '<span data-older-title>Các lần nén trước (0)</span>' +
        '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>' +
      "</button>" +
      '<div class="older-list" data-older-list hidden></div>';
    resultsEl.appendChild(olderWrap);

    olderToggle = olderWrap.querySelector(".older-toggle");
    olderList = olderWrap.querySelector("[data-older-list]");
    olderTitle = olderWrap.querySelector("[data-older-title]");

    olderToggle.addEventListener("click", function () {
      var expanded = olderToggle.getAttribute("aria-expanded") === "true";
      if (expanded) {
        var done = anim(olderList, { opacity: [1, 0] }, { duration: 0.12 });
        done.then(function () {
          olderList.hidden = true;
          olderList.style.opacity = "";
        });
        olderToggle.setAttribute("aria-expanded", "false");
      } else {
        olderList.hidden = false;
        olderList.style.opacity = "";
        olderToggle.setAttribute("aria-expanded", "true");
        anim(olderList, { opacity: [0, 1] }, { duration: 0.15 });
      }
    });
  }

  function collapseOlderDisclosure() {
    if (!olderWrap) return;
    olderToggle.setAttribute("aria-expanded", "false");
    olderList.hidden = true;
    olderList.style.opacity = "";
  }

  function makeOlder(batch) {
    batch.el.classList.add("is-older");
    batch.rowsEl.hidden = true;

    if (!batch.expandBtn) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost batch-expand";
      btn.setAttribute("aria-controls", batch.rowsEl.id);
      btn.setAttribute("aria-expanded", "false");
      btn.textContent = "Xem file (" + batch.total + ")";
      btn.addEventListener("click", function () {
        var expanded = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!expanded));
        batch.rowsEl.hidden = expanded;
        btn.textContent = expanded ? "Xem file (" + batch.total + ")" : "Ẩn file";
      });
      batch.expandBtn = btn;
      batch.el.querySelector(".batch-title-row").appendChild(btn);
    }
  }

  function demoteCurrent() {
    var old = currentBatch;
    if (!old) return Promise.resolve();
    currentBatch = null;
    makeOlder(old);

    var done = anim(old.el, { opacity: [1, 0], scale: [1, 0.98] }, { duration: 0.18, ease: "easeIn" });
    return done.then(function () {
      old.el.style.opacity = "";
      old.el.style.transform = "";
      ensureOlderWrap();
      olderList.insertBefore(old.el, olderList.firstChild);
      olderCount += 1;
      olderTitle.textContent = "Các lần nén trước (" + olderCount + ")";
      collapseOlderDisclosure();
    });
  }

  /* -------------------- Render details -------------------- */

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

  function renderDetails(entry, d, file) {
    var kind = statusKind(d);
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
    entry.detail.innerHTML =
      '<div class="stats">' +
        '<div class="stat"><div class="k">Trước</div><div class="v">' + esc(fmtSize(d.original_bytes)) + "</div></div>" +
        '<div class="stat"><div class="k">Sau</div><div class="v">' + esc(fmtSize(d.output_bytes)) + "</div></div>" +
        '<div class="stat"><div class="k">Giảm</div><div class="v">' + esc(reduceText) + "</div></div>" +
        '<div class="stat"><div class="k">Độ phân giải</div><div class="v">' + esc(resolutionText(d)) + "</div></div>" +
        '<div class="stat"><div class="k">Định dạng / chất lượng</div><div class="v">' + esc(qualityText(d)) + "</div></div>" +
        '<div class="stat"><div class="k">SSIM <span class="help" title="' + esc(SSIM_HELP) + '">?</span></div><div class="v">' + esc(Number(d.ssim).toFixed(4)) + "</div></div>" +
      "</div>" +
      '<div class="status-line ' + kind + '"><span class="mark" aria-hidden="true">' + statusMark(kind) + "</span><span>" + esc(d.status_message) + "</span></div>" +
      warningsHtml +
      notesHtml +
      '<div class="card-actions">' +
        '<a class="btn primary" href="/api/download/' + encodeURIComponent(d.job_id) + '">Tải về</a>' +
        (d.kind === "image" || d.kind === "pdf" ? compareBtn : "") +
        '<span class="out-name">' + esc(d.output_filename) + "</span>" +
      "</div>";

    var btn = entry.detail.querySelector("[data-compare]");
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
      '<figcaption class="' + cls + '">' + esc(label) + "</figcaption>" +
      '<div class="img-shell">' +
        '<span class="loading">Đang tạo ảnh so sánh...</span>' +
        '<img alt="' + esc(label) + '" src="' + previewUrl(which, page) + '">' +
      "</div>" +
    "</figure>";
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
          "<h3>Toàn bộ ảnh</h3>" +
          '<div class="pair">' +
            imgFigure("Bản gốc", "", "orig_full", null) +
            imgFigure("Sau nén", "out", "out_full", null) +
          "</div>" +
        "</section>" +
        '<section class="compare-block">' +
          "<h3>Cắt 100% ở giữa ảnh</h3>" +
          '<div class="pair">' +
            imgFigure("Bản gốc", "", "orig_crop", null) +
            imgFigure("Sau nén", "out", "out_crop", null) +
          "</div>" +
        "</section>";
    } else {
      var total = Number(d.page_count) || 1;
      var page = Math.max(0, Math.min(compareState.page, total - 1));
      compareState.page = page;
      html +=
        '<div class="pdf-nav">' +
          '<button class="btn ghost" type="button" data-prev aria-label="Trang trước"' + (page <= 0 ? " disabled" : "") + ">← Trước</button>" +
          "<span>Trang " + (page + 1) + " / " + total + "</span>" +
          '<button class="btn ghost" type="button" data-next aria-label="Trang sau"' + (page >= total - 1 ? " disabled" : "") + ">Sau →</button>" +
        "</div>" +
        '<div class="pair">' +
          imgFigure("Bản gốc · trang " + (page + 1), "", "orig_page", page) +
          imgFigure("Sau nén · trang " + (page + 1), "out", "out_page", page) +
        "</div>";
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

  function hasFileDrag(event) {
    var dt = event.dataTransfer;
    if (!dt) return false;
    if (dt.types) {
      for (var i = 0; i < dt.types.length; i++) {
        if (dt.types[i] === "Files") return true;
      }
    }
    return false;
  }

  function showPageDrop(show) {
    if (pageDrop) pageDrop.hidden = !show;
    dropzone.classList.toggle("dragging", show);
  }

  ["dragenter", "dragover", "dragleave", "drop"].forEach(function (name) {
    document.addEventListener(name, function (e) { e.preventDefault(); });
  });

  document.addEventListener("dragenter", function (e) {
    if (!hasFileDrag(e)) return;
    dragDepth += 1;
    showPageDrop(true);
  });

  document.addEventListener("dragover", function (e) {
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    if (hasFileDrag(e)) showPageDrop(true);
  });

  document.addEventListener("dragleave", function () {
    if (dragDepth === 0) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) showPageDrop(false);
  });

  document.addEventListener("drop", function (e) {
    dragDepth = 0;
    showPageDrop(false);
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      addFiles(e.dataTransfer.files);
    }
  });

  modal.addEventListener("click", function (e) {
    var target = e.target;
    if (target && target.hasAttribute && target.hasAttribute("data-close")) closeCompare();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeCompare();
  });
})();
