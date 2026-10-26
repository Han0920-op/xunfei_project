(() => {
  const paths = {
    wheat:
      '<path d="M12 22V3m0 15c-5 0-7-3-7-6 4 0 7 2 7 6Zm0-5c-5 0-7-3-7-6 4 0 7 2 7 6Zm0 5c5 0 7-3 7-6-4 0-7 2-7 6Zm0-5c5 0 7-3 7-6-4 0-7 2-7 6Zm0-6c-3-2-3-4 0-6 3 2 3 4 0 6Z"/>',
    camera:
      '<path d="M8 5 10 2h4l2 3h5v15H3V5Z"/><circle cx="12" cy="12" r="4"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    leaf: '<path d="M20 3C7 2 2 9 6 16s16 2 14-13Z"/><path d="M4 21 16 9M10 15v-5m0 5h5"/>',
    book: '<path d="M12 5v16M3 3c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2Z"/>',
    history: '<path d="M3 11a9 9 0 1 1 2.5 7M3 4v7h7M12 7v5l3 2"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4m0 3h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="m22 2-11 11"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  };
  const esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const icon = (name) =>
    `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.leaf}</svg>`;
  const day = (s) => (s ? String(s).slice(0, 10).replaceAll("-", ".") : "");
  function toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    el.textContent = text;
    document.getElementById("toasts").append(el);
    setTimeout(() => el.remove(), 5000);
  }
  let priorFocus;
  function modal(title, body, onSubmit, submit = "保存") {
    const d = document.getElementById("dialog");
    if (d.open) d.close();
    priorFocus = document.activeElement;
    d.innerHTML = `<form><header><h2 id="dialogTitle">${esc(title)}</h2><button class="icon-button" type="button" data-close aria-label="关闭">${icon("close")}</button></header><div class="dialog-body">${body}<p id="dialogError" class="error" role="alert"></p></div><footer><button type="button" class="button secondary" data-close>关闭</button>${onSubmit ? `<button class="button primary" type="submit">${esc(submit)}</button>` : ""}</footer></form>`;
    d.setAttribute("aria-labelledby", "dialogTitle");
    d.querySelectorAll("[data-close]").forEach(
      (b) => (b.onclick = () => d.close()),
    );
    d.querySelector("form").onsubmit = async (e) => {
      e.preventDefault();
      if (!onSubmit) return;
      const b = e.target.querySelector("[type=submit]");
      b.disabled = true;
      try {
        await onSubmit(new FormData(e.target));
      } catch (err) {
        document.getElementById("dialogError").textContent = err.message;
      } finally {
        if (b.isConnected) b.disabled = false;
      }
    };
    d.onclick = (e) => {
      if (e.target === d) {
        const r = d.getBoundingClientRect();
        if (
          e.clientX < r.left ||
          e.clientX > r.right ||
          e.clientY < r.top ||
          e.clientY > r.bottom
        )
          d.close();
      }
    };
    d.showModal();
    return d;
  }
  window.addEventListener("DOMContentLoaded", () =>
    document.getElementById("dialog").addEventListener("close", () => {
      if (!document.getElementById("dialog").open) priorFocus?.focus?.();
    }),
  );
  window.FarmerUI = {
    esc,
    icon,
    day,
    toast,
    modal,
    close: () => document.getElementById("dialog").close(),
  };
})();
