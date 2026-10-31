(() => {
  window.PersonalReady ||= fetch("/api/personal/session");
  document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(location.search);
    if (params.has("medicine")) {
      const input = document.querySelector("#messageInput");
      if (input) {
        input.value = "请读取我的农药库，帮我核对手里的药。";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    function cards() {
      const main = document.querySelector("#main");
      if (!main) return;
      const id = new URLSearchParams(location.search).get("record");
      const record = id ? window.FarmerStore?.get(id) : null;
      if (!record) return;
      for (const message of record.messages || [])
        for (const t of message.toolResults || []) {
          if (
            !["prepare_weather_check", "prepare_reminder"].includes(t.tool) ||
            t.result?.status !== "draft"
          )
            continue;
          const key = record.id + "-" + message.id;
          if (document.getElementById(key)) continue;
          const r = t.result;
          const card = document.createElement("section");
          card.id = key;
          card.className = "reminder-draft";
          const h = document.createElement("h3");
          h.textContent = "确认设置提醒";
          const p = document.createElement("p");
          p.textContent =
            (r.recurrence === "once"
              ? new Date(r.next || r.run_at).toLocaleString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                })
              : "每天 " + r.time) +
            " · " +
            (r.name || "天气检查") +
            (r.location ? " · " + r.location : "");
          const note = document.createElement("p");
          note.textContent = r.notes || r.concern || "";
          const status = document.createElement("p");
          status.setAttribute("role", "status");
          const button = document.createElement("button");
          button.className = "button primary";
          button.textContent = "确认设置";
          const link = document.createElement("a");
          link.className = "button secondary";
          link.href = "personal.html?tab=tasks";
          link.textContent = "去提醒页查看";
          link.hidden = true;
          button.onclick = async () => {
            button.disabled = true;
            try {
              await window.PersonalReady;
              const body = {
                name: r.name || "每日天气检查",
                notes: r.notes || r.concern || "",
                task_type:
                  r.task_type ||
                  (t.tool === "prepare_reminder" ? "reminder" : "weather"),
                recurrence: r.recurrence || "daily",
                run_at: r.run_at || "",
                time: r.time || "08:00",
                location: r.location || "",
                enabled: true,
              };
              const response = await fetch(
                "/api/personal/tasks/" + encodeURIComponent(key),
                {
                  method: "PUT",
                  headers: {
                    "Content-Type": "application/json",
                    "X-Zhimai-Personal": "1",
                  },
                  body: JSON.stringify(body),
                },
              );
              const result = await response.json();
              if (!response.ok)
                throw Error(
                  typeof result.detail === "string"
                    ? result.detail
                    : "设置失败，请检查时间",
                );
              status.textContent = "已设置，已保存到“提醒”页。";
              button.textContent = "已设置";
              link.hidden = false;
              window.ZhimaiReminders?.refresh();
            } catch (e) {
              status.textContent = e.message;
              button.disabled = false;
            }
          };
          card.append(h, p, note, button, link, status);
          main.append(card);
        }
    }
    new MutationObserver(cards).observe(document.querySelector("#main"), {
      childList: true,
      subtree: true,
    });
    cards();
  });
})();
