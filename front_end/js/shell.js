/* One navigation shell shared by chat, history, inventory and reminders. */
(() => {
  const { icon } = window.FarmerUI;
  const links = [
    ["chat", "问智麦", "index.html", "leaf"],
    ["history", "我的记录", "history.html", "history"],
    ["medicines", "我的农药库", "personal.html?tab=medicines", "book"],
    ["reminders", "提醒", "personal.html?tab=tasks", "clock"],
  ];
  function markup(active, chat = false) {
    return `<a class="skip-link" href="#main">跳到主要内容</a>
      <button class="mobile-menu icon-button" aria-label="打开导航" aria-expanded="false" aria-controls="appSidebar">${icon("more")}</button>
      <button class="sidebar-backdrop" aria-label="关闭导航" hidden></button>
      <aside class="app-sidebar" id="appSidebar" aria-label="智麦导航">
        <a class="brand sidebar-brand" href="index.html" aria-label="智麦首页"><span>${icon("wheat")}</span><b>智麦<small>小麦的事，一起看看</small></b></a>
        <span class="nav-caption">我的田间助手</span>
        <nav aria-label="主导航">${links.map(([id, label, href, ic]) => `<a href="${href}" ${id === active ? 'class="active" aria-current="page"' : ""}>${icon(ic)}<span>${label}</span>${id === active ? '<i aria-hidden="true"></i>' : ""}</a>`).join("")}</nav>
        <div class="sidebar-bottom"><div class="sidebar-note">${icon("wheat")}<p>先查清原因，<br>再安心管好麦田。</p></div>${chat ? `<button class="sidebar-help" data-action="help">${icon("help")}怎么使用智麦</button>` : '<a class="sidebar-help" href="index.html">' + icon("leaf") + "有问题，问智麦</a>"}<small>专注冬小麦 · 陪你找到下一步</small></div>
      </aside>
      <div class="app-workspace"><main id="main" tabindex="-1"></main><footer class="site-footer"><span>冬小麦病虫害辅助诊断 · 用药核对 · 持续复查</span>${chat ? '<button data-action="scope">功能范围与数据说明</button>' : "<span>资料由你确认，用药仍需核对</span>"}</footer></div>
      ${chat ? '<input id="photoInput" class="sr-only" tabindex="-1" type="file" accept="image/jpeg,image/png,image/webp">' : ""}<dialog id="dialog"></dialog><div id="toasts" aria-live="polite"></div>`;
  }
  document.addEventListener("click", (e) => {
    if (e.target.closest(".mobile-menu")) toggle(true);
    if (e.target.closest(".sidebar-backdrop")) toggle(false);
  });
  function toggle(open) {
    document.body.classList.toggle("nav-open", open);
    const b = document.querySelector(".mobile-menu");
    b?.setAttribute("aria-expanded", String(open));
    document.querySelector(".sidebar-backdrop").hidden = !open;
    if (open) document.querySelector("nav a[aria-current]")?.focus();
    else b?.focus();
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("nav-open"))
      toggle(false);
  });
  window.AppShell = { markup };
})();
