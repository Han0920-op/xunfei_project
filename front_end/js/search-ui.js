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
        u.hostname.includes(".")
        ? u
        : null;
    } catch {
      return null;
    }
  }
  function sources(result) {
    const rows = (result?.results || []).filter((x) => safe(x.url));
    return `<details><summary>本次参考了 ${rows.length} 个网页</summary>${rows.map((x) => `<p><a href="${esc(safe(x.url).href)}" target="_blank" rel="noopener noreferrer">${esc(x.title || "网页来源")}</a><small> · ${esc(safe(x.url).hostname)}${x.published_on ? " · 发布 " + esc(x.published_on) : ""}</small></p><p>${esc(x.summary || "")}</p><small>${esc(x.notice || "")}</small>`).join("")}${(
      result?.results || []
    )
      .filter((x) => !x.url)
      .map(
        (x) =>
          `<p>${esc(x.title || "摘要")}：${esc(x.summary || "")}（未提供有效链接）</p>`,
      )
      .join(
        "",
      )}<p>${esc(result?.message || (!rows.length ? "没有有效网页链接。" : ""))}</p></details>`;
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
  window.SearchUI = { event, sources, end, reset: () => calls.clear() };
})();
