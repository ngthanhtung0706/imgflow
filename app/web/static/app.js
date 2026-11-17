// Gallery: xin presigned URL, PUT ảnh thẳng lên S3, rồi cứ 3 giây hỏi lại trạng thái job.
(function () {
  const form = document.getElementById("upload-form");
  const btn = document.getElementById("upload-btn");
  const statusEl = document.getElementById("upload-status");
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  const summaryEl = document.getElementById("summary");
  const STATUS_TEXT = { PENDING: "Chờ", PROCESSING: "Đang xử lý", DONE: "Xong", FAILED: "Lỗi" };
  const PARALLEL = 6;

  async function api(path, options) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, options));
    if (res.status === 401) { location.href = "/login"; throw new Error("chưa đăng nhập"); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "HTTP " + res.status);
    return data;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const files = Array.from(form.files.files);
    if (!files.length) return;
    btn.disabled = true;
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
          statusEl.textContent = `Đã tải ${done}/${uploads.length}` + (failed ? `, lỗi ${failed}` : "");
        }
      }
      await Promise.all(Array.from({ length: PARALLEL }, runOne));
      form.files.value = "";
    } catch (err) {
      statusEl.textContent = "Lỗi: " + err.message;
    } finally {
      btn.disabled = false;
    }
  });

  function card(job) {
    const el = document.createElement("div");
    el.className = "item";
    el.dataset.id = job.job_id;
    el.dataset.status = job.status;
    const thumb = job.urls
      ? `<a href="${job.urls["1080"]}" target="_blank"><img src="${job.urls.thumb}" alt="" loading="lazy"></a>`
      : `<span>${job.status === "FAILED" ? "Không xử lý được" : "Đang chờ xử lý..."}</span>`;
    const links = job.urls
      ? Object.keys(job.urls).map((v) => `<a href="${job.urls[v]}" target="_blank">${v}</a>`).join("")
      : "";
    el.innerHTML = `
      <div class="thumb">${thumb}</div>
      <div class="meta">
        <div class="name" title=""></div>
        <span class="badge ${job.status}">${STATUS_TEXT[job.status] || job.status}</span>
        <div class="links">${links}</div>
        ${job.status === "FAILED" ? `<div class="error small"></div>` : ""}
      </div>`;
    // Tên file và lỗi do người dùng/worker tạo ra -> gán bằng textContent để tránh chèn HTML
    const name = el.querySelector(".name");
    name.textContent = (job.product ? job.product + " · " : "") + job.name;
    name.title = name.textContent;
    const errEl = el.querySelector(".error");
    if (errEl) errEl.textContent = job.error || "";
    return el;
  }

  async function refresh() {
    try {
      const data = await api("/api/jobs");
      summaryEl.innerHTML = Object.entries(data.summary)
        .map(([s, n]) => `<span class="badge ${s}">${STATUS_TEXT[s]}: ${n}</span>`).join("");
      empty.hidden = data.jobs.length > 0;
      // Chỉ vẽ lại ô nào đổi trạng thái để ảnh không nhấp nháy
      const existing = new Map(Array.from(grid.children).map((el) => [el.dataset.id, el]));
      let prev = null;
      for (const job of data.jobs) {
        let el = existing.get(job.job_id);
        if (!el || el.dataset.status !== job.status) {
          const fresh = card(job);
          if (el) el.replaceWith(fresh);
          el = fresh;
        }
        existing.delete(job.job_id);
        if (prev ? prev.nextSibling !== el : grid.firstChild !== el) {
          prev ? prev.after(el) : grid.prepend(el);
        }
        prev = el;
      }
      existing.forEach((el) => el.remove());
    } catch (err) {
      console.error(err);
    }
  }

  refresh();
  setInterval(refresh, 3000);
})();
