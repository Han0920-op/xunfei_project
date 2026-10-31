(() => {
  window.PersonalReady = fetch("/api/personal/session").catch(() => {});
  document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(location.search);
    if (params.has("medicine")) {
      const input = document.querySelector("#messageInput");
      if (input) {
        input.value = "请读取我的农药库，帮我核对手里的药。";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    const observer = new MutationObserver(() => {
      for (const record of window.FarmerStore?.records() || [])
        for (const message of record.messages || [])
          for (const t of message.toolResults || []) {
            if (
              t.tool !== "prepare_weather_check" ||
              t.result?.status !== "draft"
            )
              continue;
            const r = t.result,
              key = record.id + "-" + message.id;
            if (document.getElementById(key)) continue;
            const host = document.querySelector("#main");
            if (!host) continue;
            const a = document.createElement("a");
            a.id = key;
            a.className = "button secondary";
            a.textContent = `确认每日 ${r.time} · ${r.location} 天气检查`;
            a.href =
              "personal.html?" +
              new URLSearchParams({
                tab: "tasks",
                draft: key,
                location: r.location,
                time: r.time,
                concern: r.concern,
              });
            host.append(a);
          }
    });
    observer.observe(document.querySelector("#main"), {
      childList: true,
      subtree: true,
    });
  });
})();
