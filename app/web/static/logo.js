// Logo watermark của shop: xem, tải lên, xoá.
(function () {
  const form = document.getElementById("logo-form");
  if (!form) return;
  const img = document.getElementById("logo-preview");
  const none = document.getElementById("logo-none");
  const btn = document.getElementById("logo-btn");
  const del = document.getElementById("logo-del");
  const statusEl = document.getElementById("logo-status");

  function show(hasLogo) {
    img.hidden = !hasLogo;
    none.hidden = hasLogo;
    del.hidden = !hasLogo;
    if (hasLogo) img.src = "/api/logo?t=" + Date.now();
  }

  async function load() {
    const res = await fetch("/api/logo", { cache: "no-store" });
    if (res.status === 401) { location.href = "/login"; return; }
    show(res.ok);
  }

  async function message(res) {
    const data = await res.json().catch(() => ({}));
    return res.ok ? "" : (data.error || "HTTP " + res.status);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = form.logo.files[0];
    if (!file) return;
    btn.disabled = true;
    statusEl.textContent = "Đang lưu...";
    try {
      const body = new FormData();
      body.append("logo", file);
      const err = await message(await fetch("/api/logo", { method: "POST", body }));
      statusEl.textContent = err ? "Lỗi: " + err : "Đã lưu logo. Ảnh upload từ giờ sẽ dùng logo này.";
      form.reset();
      load();
    } catch (ex) {
      statusEl.textContent = "Lỗi: " + ex.message;
    } finally {
      btn.disabled = false;
    }
  });

  del.addEventListener("click", async () => {
    const err = await message(await fetch("/api/logo", { method: "DELETE" }));
    statusEl.textContent = err ? "Lỗi: " + err : "Đã xoá logo riêng, dùng lại logo mặc định.";
    load();
  });

  load();
})();
