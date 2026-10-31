/* Reminder confirmations belong to the reply, not an observer below the composer. */
(() => {
  const { esc, icon } = window.FarmerUI;
  const bindings = new Map(),
    states = new Map();
  function markup(recordId, message) {
    return (message.toolResults || [])
      .map((tool, index) => {
        if (
          !["prepare_weather_check", "prepare_reminder"].includes(tool.tool) ||
          tool.result?.status !== "draft"
        )
          return "";
        const r = tool.result,
          key = recordId + "-" + message.id + (index ? "-" + index : "");
        const recurrence = r.recurrence || (r.run_at ? "once" : "daily");
        if (
          (recurrence === "once" && !(r.run_at || r.next)) ||
          (recurrence === "daily" && !r.time)
        )
          return '<p class="error">提醒草案缺少具体时间，请重新说明日期和时间，或<a href="personal.html?tab=tasks">手动设置提醒</a>。</p>';
        const body = {
          name: r.name || "每日天气检查",
          notes: r.notes || r.concern || "",
          task_type:
            r.task_type ||
            (tool.tool === "prepare_reminder" ? "reminder" : "weather"),
          recurrence,
          run_at: r.run_at || (recurrence === "once" ? r.next : ""),
          time: r.time || "08:00",
          location: r.location || "",
          enabled: true,
        };
        bindings.set(key, body);
        const state = states.get(key) || {};
        const date = body.run_at;
        const parsed = new Date(
          date && !/(Z|[+-]\d{2}:\d{2})$/.test(date) ? date + "+08:00" : date,
        );
        const label =
          recurrence === "once"
            ? parsed.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
            : "每天 " + body.time;
        return `<section class="reminder-draft" data-reminder-key="${esc(key)}" aria-label="提醒确认卡"><h3>${icon("clock")}确认设置提醒</h3><p>${esc(label)} · 北京时间${body.location ? " · " + esc(body.location) : ""}</p><p>${esc(body.name)}</p>${body.notes ? `<p>${esc(body.notes)}</p>` : ""}<div class="reminder-draft-actions"><button type="button" class="button primary" data-reminder-confirm="${esc(key)}" ${state.saving || state.saved ? "disabled" : ""}>${state.saved ? "已设置" : state.saving ? "正在保存…" : "确认设置"}</button><a class="button secondary" href="personal.html?tab=tasks">${state.saved ? "去提醒页查看" : "查看我的提醒"}</a></div><p data-reminder-status role="status">${esc(state.message || "尚未保存，点击确认后才会启用。")}</p></section>`;
      })
      .join("");
  }
  function update(key) {
    for (const card of document.querySelectorAll("[data-reminder-key]")) {
      if (card.dataset.reminderKey !== key) continue;
      const s = states.get(key);
      const b = card.querySelector("[data-reminder-confirm]");
      b.disabled = Boolean(s.saved || s.saving);
      b.textContent = s.saved ? "已设置" : s.saving ? "正在保存…" : "确认设置";
      card.querySelector("[data-reminder-status]").textContent =
        s.message || "";
      if (s.saved) card.querySelector("a").textContent = "去提醒页查看";
    }
  }
  document.addEventListener("click", async (e) => {
    const button = e.target.closest("[data-reminder-confirm]");
    if (!button) return;
    const key = button.dataset.reminderConfirm,
      body = bindings.get(key),
      state = states.get(key) || {};
    if (!body || state.saving || state.saved) return;
    states.set(key, { saving: true, message: "正在保存提醒…" });
    update(key);
    try {
      await window.PersonalReady;
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
            : "设置失败，请检查日期和时间",
        );
      states.set(key, { saved: true, message: "已设置，已保存到“提醒”页。" });
      window.ZhimaiReminders?.refresh();
    } catch (error) {
      states.set(key, { message: error.message || "保存失败，请重试。" });
    }
    update(key);
  });
  window.ReminderCards = { markup };
})();
