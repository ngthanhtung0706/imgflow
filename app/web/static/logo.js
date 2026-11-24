// Logo watermark của shop: xem, chọn file là tự lưu, quay về logo mặc định.
(function () {
  const form = document.getElementById("logo-form");
  if (!form) return;
  const input = form.logo;
  const img = document.getElementById("logo-preview");
  const none = document.getElementById("logo-none");
  const nameEl = document.getElementById("logo-name");
  const pick = document.getElementById("logo-pick");
  const del = document.getElementById("logo-del");
  const statusEl = document.getElementById("logo-status");
  const MAX_BYTES = 512 * 1024;

  function show(hasLogo) {
    img.hidden = !hasLogo;
    none.hidden = hasLogo;
    del.hidden = !hasLogo;
    nameEl.textContent = hasLogo ? "Logo riêng của shop" : "Logo mặc định";
    pick.lastChild.textContent = hasLogo ? "Đổi logo" : "Chọn logo";
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

  async function upload(file) {
    // kiểm tra ngay trên trình duyệt, máy chủ vẫn kiểm tra lại
    if (file.type !== "image/png") { statusEl.textContent = "Logo phải là file PNG."; return; }
    if (file.size > MAX_BYTES) { statusEl.textContent = "Logo tối đa 512 KB."; return; }
    pick.classList.add("busy");
    statusEl.textContent = "Đang lưu...";
    try {
      const body = new FormData();
      body.append("logo", file);
      const err = await message(await fetch("/api/logo", { method: "POST", body }));
      statusEl.textContent = err || "Đã lưu. Áp dụng cho ảnh tải lên từ bây giờ.";
      await load();
    } catch (ex) {
      statusEl.textContent = "Lỗi: " + ex.message;
    } finally {
      pick.classList.remove("busy");
      input.value = "";
    }
  }

  input.addEventListener("change", () => { if (input.files[0]) upload(input.files[0]); });
  form.addEventListener("submit", (e) => { e.preventDefault(); if (input.files[0]) upload(input.files[0]); });

  del.addEventListener("click", async () => {
    const err = await message(await fetch("/api/logo", { method: "DELETE" }));
    statusEl.textContent = err || "Đã chuyển về logo mặc định.";
    load();
  });

  load();
})();
