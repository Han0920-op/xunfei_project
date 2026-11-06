/* Keep chat documents and their live streams mounted during in-app navigation. */
(() => {
  "use strict";
  const pages = new Set([
    "index.html",
    "history.html",
    "personal.html",
    "memory.html",
    "plans.html",
    "intelligence.html",
    "weather-alerts.html",
  ]);
  const urlFor = (href) => {
    const u = new URL(href, location.href);
    return u.origin === location.origin &&
      pages.has(u.pathname.split("/").pop())
      ? u
      : null;
  };
  let host = null;
  try {
    if (parent !== window && parent.ChatNavigation?.host)
      host = parent.ChatNavigation;
  } catch (_) {}
  const isChat = (u) =>
    u.pathname.endsWith("/index.html") || u.pathname === "/";
  // Standalone management pages retain their existing navigation behavior.
  if (!host && document.body.dataset.screen === "chat") {
    const entries = new Map();
    let sequence = 0,
      active,
      lastChat;
    const initial = {
      id: "chat-0",
      url: new URL(location.href),
      win: window,
      frame: null,
      title: document.title,
      scroll: 0,
      chat: true,
    };
    entries.set(initial.id, initial);
    active = lastChat = initial;
    const state = (entry) => ({ zhimaiView: entry.id });
    history.replaceState(state(initial), "", initial.url);
    function identify(win) {
      return [...entries.values()].find(
        (e) => e.win === win || e.frame?.contentWindow === win,
      );
    }
    function show(entry, push = true) {
      const previous = active;
      active.scroll = active.win?.scrollY || 0;
      const app = document.getElementById("app");
      if (active.frame) active.frame.hidden = true;
      app.style.display = entry === initial ? "" : "none";
      app.inert = entry !== initial;
      for (const view of [active, entry]) {
        const doc = view.win?.document;
        doc?.body.classList.remove("nav-open");
        const backdrop = doc?.querySelector(".sidebar-backdrop");
        if (backdrop) backdrop.hidden = true;
        doc
          ?.querySelector(".mobile-menu")
          ?.setAttribute("aria-expanded", "false");
      }
      document.body.style.overflow = entry === initial ? "" : "hidden";
      active = entry;
      if (entry.chat) lastChat = entry;
      if (entry.frame) entry.frame.hidden = false;
      document.title = entry.title;
      if (push) history.pushState(state(entry), "", entry.url);
      else history.replaceState(state(entry), "", entry.url);
      entry.win?.requestAnimationFrame(() =>
        entry.win.scrollTo(0, entry.scroll),
      );
      entry.win?.dispatchEvent(new Event("zhimai:resume"));
      if (previous !== initial && !previous.chat && previous !== entry) {
        previous.frame.remove();
        entries.delete(previous.id);
      }
    }
    function open(href, source = window, fresh = false, push = true) {
      let url = urlFor(href);
      if (!url) return false;
      if (isChat(url) && !url.search && !fresh) {
        show(lastChat, push);
        return true;
      }
      if (fresh) url.searchParams.set("new", window.FarmerStore.id());
      let entry = [...entries.values()].find(
        (e) => e.chat && e.url.href === url.href,
      );
      if (!entry) {
        const frame = document.createElement("iframe");
        frame.title = isChat(url) ? "智麦对话" : "智麦功能页面";
        frame.className = "app-navigation-view";
        frame.style.cssText =
          "position:fixed;inset:0;width:100%;height:100%;border:0;background:#fafbf6;z-index:100;";
        entry = {
          id: "view-" + ++sequence,
          url,
          frame,
          win: null,
          title: "智麦",
          scroll: 0,
          chat: isChat(url),
        };
        entries.set(entry.id, entry);
        frame.addEventListener("load", () => {
          entry.win = frame.contentWindow;
          entry.title = frame.contentDocument?.title || "智麦";
          const loaded = urlFor(entry.win.location.href);
          if (loaded) {
            entry.url = loaded;
            entry.chat = isChat(loaded);
          }
          if (active === entry)
            history.replaceState(state(entry), "", entry.url);
          if (active === entry) document.title = entry.title;
        });
        frame.src = url.href;
        document.body.append(frame);
        entry.win = frame.contentWindow;
      }
      // Management screens reload on return so newly saved medicines/tasks appear.
      show(entry, push);
      return true;
    }
    function replace(href, source = window) {
      const entry = identify(source),
        url = urlFor(href);
      if (!entry || !url) return;
      entry.url = url;
      if (source !== window) source.history.replaceState(null, "", url);
      if (active === entry) history.replaceState(state(entry), "", url);
    }
    host = window.ChatNavigation = {
      host: true,
      open,
      replace,
      isActive: (source = window) => identify(source) === active,
    };
    window.addEventListener("popstate", (event) => {
      const entry = entries.get(event.state?.zhimaiView);
      if (entry) show(entry, false);
      else open(location.href, window, false, false);
    });
  }
  if (!host) {
    window.ChatNavigation = {
      go: (href) => location.assign(href),
      replace: (href) => history.replaceState(null, "", href),
    };
    return;
  }
  if (parent !== window)
    window.ChatNavigation = {
      isActive: () => host.isActive(window),
      go: (href) => host.open(href, window),
      replace: (href) => host.replace(href, window),
    };
  else window.ChatNavigation.go = (href) => host.open(href, window);
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (
      !link ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      link.hasAttribute("download") ||
      (link.target && link.target !== "_self") ||
      link.getAttribute("href").startsWith("#")
    )
      return;
    if (urlFor(link.href)) {
      event.preventDefault();
      host.open(link.href, window, link.hasAttribute("data-new-chat"));
    }
  });
})();
