(() => {
  const { esc } = FarmerUI;
  const calls = new Map();
  function safe(value) {
    try {
      const u = new URL(value);
      return ["https:", "http:"].includes(u.protocol) &&
        !u.username &&
        !u.password &&
        !["localhost", "127.0.0.1", "::1"].includes(u.hostname) &&
        !u.hostname.endsWith(".local") &&
        !u.hostname.endsWith(".internal") &&
        !/^(?:0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(
          u.hostname,
        ) &&
        u.hostname.includes(".")
        ? u
        : null;
    } catch {
      return null;
    }
  }
  function sources(result) {
    const rows = (Array.isArray(result?.results) ? result.results : []).filter(
      (x) => x && safe(x.url),
    );
    const query =
      typeof result?.query === "string"
        ? result.query.slice(0, 200)
        : "小麦 症状 农业农村部";
    const manual = !rows.length
      ? `<div class="search-manual"><p>尚未取得可用网页。可自行打开搜索页面，结果需要另行核对：</p><a href="https://www.bing.com/search?q=${encodeURIComponent(query)}" target="_blank" rel="noopener noreferrer">在必应搜索</a><a href="https://www.baidu.com/s?wd=${encodeURIComponent(query)}" target="_blank" rel="noopener noreferrer">在百度搜索</a></div>`
      : "";
    return `<section class="web-sources" aria-label="联网搜索相关网页"><h3>相关网页</h3><p class="source-count">本次参考了 ${rows.length} 个网页</p><div class="web-source-list">${rows
      .map((x) => {
        const u = safe(x.url),
          official =
            u.hostname === "moa.gov.cn" || u.hostname.endsWith(".moa.gov.cn");
        return `<article class="web-source-card"><small>${esc(u.hostname)}${official ? " · 农业农村部网站" : ""}${x.published_on ? " · 发布 " + esc(x.published_on) : ""}</small><h4><a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(x.title || "网页来源")}</a></h4><p>${esc(x.summary || "此网页未提供摘要，请打开原文查看。")}</p>${x.notice ? `<small>${esc(x.notice)}</small>` : ""}<a class="source-open" href="${esc(u.href)}" target="_blank" rel="noopener noreferrer" aria-label="打开原文：${esc(x.title || u.hostname)}">打开原文 ↗</a></article>`;
      })
      .join(
        "",
      )}</div><p class="search-source-note">${esc(result?.message || "网页资料供核对参考，不等于现场确诊或用药许可。")}</p>${manual}</section>`;
  }
  function forMessage(message) {
    return (message.toolResults || [])
      .filter((t) => t.tool === "search_web")
      .map((t) => sources(t.result))
      .join("");
  }
  function event(e) {
    if (e.tool !== "search_web" || !e.call_id) return;
    const old = calls.get(e.call_id);
    if (old?.terminal && e.type === "tool_start") return;
    const state = {
      terminal: e.type !== "tool_start",
      text:
        e.type === "tool_start"
          ? "正在联网搜索中……"
          : e.type === "tool_error" || e.result?.status !== "ok"
            ? "搜索失败，请重试"
            : "已完成搜索",
      result: e.result,
    };
    calls.set(e.call_id, state);
    let host = document.getElementById("liveSearch");
    if (!host) {
      host = document.createElement("section");
      host.id = "liveSearch";
      host.className = "reminder-draft";
      document.querySelector(".messages")?.append(host);
    }
    host.innerHTML = [...calls.values()]
      .map(
        (s) =>
          `<p role="status">${esc(s.text)}</p>${s.result ? sources(s.result) : ""}`,
      )
      .join("");
  }
  function end() {
    for (const [id, s] of calls)
      if (!s.terminal) {
        s.terminal = true;
        s.text = "搜索已中断，请重试";
      }
    const host = document.getElementById("liveSearch");
    if (host)
      host.innerHTML = [...calls.values()]
        .map((s) => `<p>${esc(s.text)}</p>${s.result ? sources(s.result) : ""}`)
        .join("");
  }
  window.SearchUI = {
    event,
    sources,
    forMessage,
    end,
    reset: () => calls.clear(),
  };
})();
