// Gallery: tải ảnh lên S3 bằng presigned URL, theo dõi xử lý, lọc/nhóm ảnh, xem chi tiết.
// Mọi dữ liệu do người dùng hoặc worker tạo ra (tên file, tên sản phẩm, lỗi, tên worker)
// đều gán bằng textContent, không chèn vào innerHTML.
(function () {
  const $ = (id) => document.getElementById(id);
  const STATUS_TEXT = { PENDING: "Chờ", PROCESSING: "Đang xử lý", DONE: "Xong", FAILED: "Lỗi" };
  const VARIANT_TEXT = { full: "Full", "1080": "1080 px", "600": "600 px", thumb: "Thumb" };
  const VARIANT_ORDER = ["full", "1080", "600", "thumb"];
  const PARALLEL = 6;
  const POLL_MS = 3000;

  const state = { jobs: [], status: "ALL", q: "", group: false, signature: "", modalId: null, modalSig: "", variant: "1080" };

  // ---------------------------------------------------------------- tiện ích
  async function api(path, options) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, options));
    if (res.status === 401) { location.href = "/login"; throw new Error("chưa đăng nhập"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
    return data;
  }

  function el(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  const fmtNum = (n) => n.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
  const fmtBytes = (n) => {
    if (n == null) return "–";
    if (n < 1024) return n + " B";
    if (n < 1048576) return Math.round(n / 1024) + " KB";
    return fmtNum(n / 1048576) + " MB";
  };
  const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString("vi-VN") : "–");
  const fmtSec = (s) => (s == null ? "–" : s < 60 ? fmtNum(s) + " giây" : Math.floor(s / 60) + " phút " + Math.round(s % 60) + " giây");

  // ---------------------------------------------------------------- tải ảnh lên
  const form = $("upload-form");
  const btn = $("upload-btn");
  const statusEl = $("upload-status");
  const fileInput = $("files");
  const dropzone = $("dropzone");
  const dzSub = $("dz-sub");
  const upProgress = $("up-progress");
  const upBar = $("up-bar");
  const DZ_DEFAULT = dzSub.textContent;

  function describeSelection() {
    const n = fileInput.files.length;
    if (!n) { dzSub.textContent = DZ_DEFAULT; return; }
    const total = Array.from(fileInput.files).reduce((s, f) => s + f.size, 0);
    dzSub.textContent = `Đã chọn ${n} ảnh · ${fmtBytes(total)}`;
  }
  fileInput.addEventListener("change", describeSelection);
  ["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.remove("over")));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      describeSelection();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const files = Array.from(fileInput.files);
    if (!files.length) return;
    btn.disabled = true;
    upProgress.hidden = false;
    upBar.style.width = "0";
    try {
      statusEl.textContent = `Đang xin quyền tải ${files.length} ảnh...`;
      const { uploads } = await api("/api/uploads", {
        method: "POST",
        body: JSON.stringify({
          product: form.product.value,
          files: files.map((f) => ({ name: f.name, type: f.type, size: f.size })),
        }),
      });
      refresh();

      let done = 0, failed = 0, next = 0;
      async function runOne() {
        while (next < uploads.length) {
          const i = next++;
          const u = uploads[i];
          try {
            const res = await fetch(u.url, { method: "PUT", headers: u.headers, body: files[i] });
            if (!res.ok) throw new Error("S3 " + res.status);
            done++;
          } catch (err) {
            console.error(u.name, err);
            failed++;
          }
          upBar.style.width = Math.round(((done + failed) / uploads.length) * 100) + "%";
          statusEl.textContent = `Đã tải ${done}/${uploads.length}` + (failed ? `, lỗi ${failed}` : "");
        }
      }
      await Promise.all(Array.from({ length: PARALLEL }, runOne));
      fileInput.value = "";
      describeSelection();
      statusEl.textContent += failed ? "" : " · xong, đang xử lý ảnh...";
    } catch (err) {
      statusEl.textContent = "Lỗi: " + err.message;
    } finally {
      btn.disabled = false;
      setTimeout(() => { upProgress.hidden = true; }, 1500);
    }
  });

  // ---------------------------------------------------------------- bảng theo dõi
  function renderStats(summary, stats) {
    const total = Object.values(summary).reduce((a, b) => a + b, 0);
    const active = (summary.PENDING || 0) + (summary.PROCESSING || 0);
    $("st-total").textContent = total;
    $("st-done").textContent = summary.DONE || 0;
    $("st-active").textContent = active;
    $("st-failed").textContent = summary.FAILED || 0;
    const finished = (summary.DONE || 0) + (summary.FAILED || 0);
    const pct = total ? Math.round((finished / total) * 100) : 0;
    $("st-bar").style.width = pct + "%";
    $("st-progress").setAttribute("aria-valuenow", pct);
    $("st-pct").textContent = pct + "% đã xử lý";

    ["ALL", "PENDING", "PROCESSING", "DONE", "FAILED"].forEach((s) => {
      $("c-" + s).textContent = s === "ALL" ? total : summary[s] || 0;
    });

    if (!stats) return;
    $("st-rate").textContent = stats.done_last_minute;
    $("st-avg").textContent = fmtSec(stats.avg_seconds);
    $("st-workers").textContent = stats.workers.length;
  }

  // ---------------------------------------------------------------- lưới ảnh
  function matches(job) {
    if (state.status !== "ALL" && job.status !== state.status) return false;
    if (!state.q) return true;
    const hay = ((job.product || "") + " " + job.name).toLowerCase();
    return hay.includes(state.q);
  }

  function card(job) {
    const item = el("button", "item");
    item.type = "button";
    item.dataset.id = job.job_id;
    const thumb = el("div", "thumb");
    if (job.urls) {
      const img = document.createElement("img");
      img.src = job.urls.thumb;
      img.alt = job.name;
      img.loading = "lazy";
      thumb.append(img);
    } else if (job.status === "FAILED") {
      thumb.classList.add("failed");
      thumb.textContent = "Không xử lý được";
    } else {
      thumb.classList.add("skeleton", job.status);
      thumb.setAttribute("role", "img");
      thumb.setAttribute("aria-label", job.status === "PROCESSING" ? "Đang xử lý" : "Đang chờ xử lý");
    }
    const meta = el("div", "meta");
    const name = el("div", "name", job.name);
    name.title = job.name;
    meta.append(name, el("span", "badge " + job.status, STATUS_TEXT[job.status] || job.status));
    if (job.status === "DONE" && job.duration_s != null) meta.append(el("span", "sub", fmtSec(job.duration_s)));
    if (job.status === "FAILED") meta.append(el("div", "error", job.error || "Lỗi không rõ."));
    item.append(thumb, meta);
    item.addEventListener("click", () => openModal(job.job_id));
    return item;
  }

  function renderGallery() {
    const list = state.jobs.filter(matches);
    const signature = JSON.stringify([state.status, state.q, state.group, list.map((j) => [j.job_id, j.status, j.duration_s])]);
    $("result-count").textContent = state.jobs.length ? `Hiển thị ${list.length}/${state.jobs.length} ảnh` : "";
    $("empty").hidden = state.jobs.length > 0;
    if (state.jobs.length && !list.length) {
      $("empty").hidden = false;
      $("empty").textContent = "Không có ảnh nào khớp bộ lọc.";
    } else {
      $("empty").textContent = "Chưa có ảnh nào. Hãy tải ảnh lên để bắt đầu.";
    }
    if (signature === state.signature) return; // không đổi thì không vẽ lại, ảnh khỏi nhấp nháy
    state.signature = signature;

    const root = $("gallery");
    if (!state.group) {
      const grid = el("div", "grid");
      grid.append(...list.map(card));
      root.replaceChildren(grid);
      return;
    }
    const groups = new Map();
    list.forEach((j) => {
      const key = j.product || "Không có sản phẩm";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(j);
    });
    const parts = [];
    groups.forEach((jobs, key) => {
      const title = el("div", "group-title", key);
      title.append(el("span", "", jobs.length + " ảnh"));
      const grid = el("div", "grid");
      grid.append(...jobs.map(card));
      parts.push(title, grid);
    });
    root.replaceChildren(...parts);
  }

  $("filters").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    state.status = chip.dataset.status;
    document.querySelectorAll("#filters .chip").forEach((c) => c.classList.toggle("active", c === chip));
    renderGallery();
  });
  $("q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); renderGallery(); });
  $("group").addEventListener("change", (e) => { state.group = e.target.checked; renderGallery(); });

  // ---------------------------------------------------------------- khung xem chi tiết
  const modal = $("modal");

  function currentList() { return state.jobs.filter(matches); }

  function renderModal() {
    const job = state.jobs.find((j) => j.job_id === state.modalId);
    if (!job) { closeModal(); return; }
    const list = currentList();
    const idx = list.findIndex((j) => j.job_id === state.modalId);
    $("m-prev").disabled = idx <= 0;
    $("m-next").disabled = idx < 0 || idx >= list.length - 1;
    // Không vẽ lại khung khi dữ liệu của ảnh này không đổi, để ảnh khỏi nhấp nháy mỗi 3 giây
    const sig = JSON.stringify([job.job_id, state.variant, job.status, job.finished_at, job.error]);
    if (sig === state.modalSig) return;
    state.modalSig = sig;
    $("m-title").textContent = (job.product ? job.product + " · " : "") + job.name;

    const preview = $("m-preview");
    const tabs = $("m-variants");
    const open = $("m-open");
    if (job.urls) {
      if (!job.urls[state.variant]) state.variant = "1080";
      const img = document.createElement("img");
      img.src = job.urls[state.variant];
      img.alt = job.name;
      preview.replaceChildren(img);
      tabs.replaceChildren(...VARIANT_ORDER.filter((v) => job.urls[v]).map((v) => {
        const b = el("button", v === state.variant ? "active" : "", VARIANT_TEXT[v] || v);
        b.type = "button";
        b.addEventListener("click", () => { state.variant = v; state.modalSig = ""; renderModal(); });
        return b;
      }));
      open.href = job.urls[state.variant];
      open.hidden = false;
    } else {
      preview.textContent = job.status === "FAILED" ? "Ảnh này không xử lý được." : "Ảnh đang được xử lý, vui lòng chờ...";
      tabs.replaceChildren();
      open.hidden = true;
    }

    const rows = [
      ["Trạng thái", el("span", "badge " + job.status, STATUS_TEXT[job.status] || job.status)],
      ["Sản phẩm", job.product || "–"],
      ["Dung lượng ảnh gốc", fmtBytes(job.size_bytes)],
      ["Tải lên lúc", fmtTime(job.created_at)],
      ["Bắt đầu xử lý", fmtTime(job.started_at)],
      ["Xong lúc", fmtTime(job.finished_at)],
      ["Thời gian xử lý", fmtSec(job.duration_s)],
      ["Số lần thử", String(job.attempts)],
      ["Worker xử lý", job.worker || "–"],
    ];
    const info = $("m-info");
    info.replaceChildren();
    rows.forEach(([k, v]) => {
      const dd = el("dd");
      if (typeof v === "string") dd.textContent = v; else dd.append(v);
      info.append(el("dt", "", k), dd);
    });
    const err = $("m-error");
    err.hidden = !(job.status === "FAILED");
    err.textContent = job.error ? "Lý do lỗi: " + job.error : "";
  }

  function openModal(id) {
    state.modalId = id;
    state.modalSig = "";
    modal.hidden = false;
    document.body.classList.add("modal-open");
    renderModal();
  }
  function closeModal() {
    state.modalId = null;
    state.modalSig = "";
    modal.hidden = true;
    document.body.classList.remove("modal-open");
  }
  function step(delta) {
    const list = currentList();
    const idx = list.findIndex((j) => j.job_id === state.modalId);
    const target = list[idx + delta];
    if (target) { state.modalId = target.job_id; state.modalSig = ""; renderModal(); }
  }
  modal.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeModal(); });
  $("m-prev").addEventListener("click", () => step(-1));
  $("m-next").addEventListener("click", () => step(1));
  document.addEventListener("keydown", (e) => {
    if (modal.hidden) return;
    if (e.key === "Escape") closeModal();
    else if (e.key === "ArrowLeft") step(-1);
    else if (e.key === "ArrowRight") step(1);
  });

  // ---------------------------------------------------------------- cập nhật định kỳ
  let busy = false;
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const [data, stats] = await Promise.all([api("/api/jobs"), api("/api/stats").catch(() => null)]);
      state.jobs = data.jobs;
      $("updated").textContent = "Cập nhật lúc " + new Date().toLocaleTimeString("vi-VN");
      renderStats(data.summary, stats);
      renderGallery();
      if (state.modalId) renderModal();
    } catch (err) {
      console.error(err);
    } finally {
      busy = false;
    }
  }

  refresh();
  setInterval(refresh, POLL_MS);
})();
