/* Global inbox delivery: works on every page, even without desktop permission. */
(() => {
  window.PersonalReady ||= fetch("/api/personal/session")
    .then((r) => r.ok)
    .catch(() => false);
  let busy = false,
    current = null,
    rows = [];
  const delivered = new Set();
  async function api(path, method = "GET") {
    const r = await fetch("/api/personal/" + path, {
      method,
      headers: { "X-Zhimai-Personal": "1" },
      cache: "no-store",
    });
    if (!r.ok) throw Error("提醒连接暂不可用");
    return r.json();
  }
  function badge(count) {
    const link = document.querySelector(
      'nav a[href="personal.html?tab=tasks"]',
    );
    if (!link) return;
    link.setAttribute("aria-label", "提醒");
    let b = link.querySelector(".reminder-count");
    if (!b) {
      b = document.createElement("span");
      b.className = "reminder-count";
      b.setAttribute("aria-hidden", "true");
      link.append(b);
    }
    b.textContent = count ? String(count) : "";
    b.hidden = !count;
  }
  function show(item, test = false) {
    if (current) return;
    current = item;
    const box = document.createElement("section");
    box.id = "reminderAlert";
    box.className = "reminder-alert";
    box.setAttribute("role", "alertdialog");
    box.setAttribute("aria-live", "assertive");
    box.setAttribute("aria-labelledby", "reminderAlertTitle");
    box.setAttribute("aria-describedby", "reminderAlertMessage");
    const title = document.createElement("h2");
    title.id = "reminderAlertTitle";
    title.textContent = item.name;
    const p = document.createElement("p");
    p.id = "reminderAlertMessage";
    p.textContent = item.message;
    const label = document.createElement("small");
    label.textContent = item.is_demo
      ? "天气情景演示 · 非真实预警"
      : item.task_type === "weather_alert"
        ? "官方天气预警 · 请核对发布时间和范围"
        : test
          ? "测试提醒 · 不会创建真实任务"
          : "智麦提醒 · 已到约定时间";
    const actions = document.createElement("div");
    const link = document.createElement("a");
    link.href =
      item.task_type === "weather_alert"
        ? "weather-alerts.html"
        : item.case_id
          ? "memory.html?case=" + encodeURIComponent(item.case_id)
          : "personal.html?tab=notifications";
    link.textContent =
      item.task_type === "weather_alert"
        ? "查看防护建议"
        : item.case_id
          ? "回到案例补图与复查"
          : "查看提醒";
    link.className = "button secondary";
    const ack = document.createElement("button");
    ack.className = "button primary";
    ack.textContent = "知道了";
    ack.onclick = async () => {
      ack.disabled = true;
      try {
        if (!test)
          await api(
            "notifications/" + encodeURIComponent(item.id) + "/read",
            "POST",
          );
        box.remove();
        current = null;
        await poll();
      } catch {
        ack.disabled = false;
        ack.textContent = "确认失败，点此重试";
      }
    };
    actions.append(link, ack);
    box.append(label, title, p);
    if (item.task_type === "weather_alert") {
      const advice = document.createElement("ol");
      for (const text of item.advice || []) {
        const li = document.createElement("li");
        li.textContent = text;
        advice.append(li);
      }
      const note = document.createElement("small");
      note.textContent = item.notice || "";
      box.append(advice, note);
    }
    box.append(actions);
    document.body.append(box);
  }
  async function poll() {
    if (busy) return;
    busy = true;
    try {
      await window.PersonalReady;
      rows = await api("notifications");
      const unread = rows.filter(
        (x) =>
          !x.read &&
          !x.superseded &&
          !(
            x.task_type === "weather_alert" &&
            x.warning?.status === "active" &&
            Date.parse(x.warning.expires_at) <= Date.now()
          ),
      );
      if (
        current?.id &&
        !current.is_demo &&
        !unread.some((x) => x.id === current.id)
      ) {
        document.getElementById("reminderAlert")?.remove();
        current = null;
      }
      badge(unread.length);
      for (const item of unread) {
        if (
          item.task_type === "weather_alert" &&
          item.warning?.status === "active" &&
          Date.parse(item.warning.expires_at) <= Date.now()
        )
          continue;
        if (
          ["regional", "weather_alert"].includes(item.task_type) &&
          !item.urgent &&
          item.quiet_start &&
          item.quiet_end
        ) {
          const clock = new Date().toLocaleTimeString("sv-SE", {
              timeZone: "Asia/Shanghai",
              hour: "2-digit",
              minute: "2-digit",
            }),
            s = item.quiet_start,
            e = item.quiet_end;
          if (
            s !== e &&
            (s < e ? s <= clock && clock < e : clock >= s || clock < e)
          )
            continue;
        }
        if (!delivered.has(item.id)) {
          delivered.add(item.id);
          if (
            item.task_type !== "weather_alert" &&
            "Notification" in window &&
            Notification.permission === "granted"
          ) {
            try {
              const n = new Notification(item.name, {
                body: item.message,
                tag: item.id,
                requireInteraction: true,
              });
              n.onclick = () => {
                window.focus();
                location.href = item.case_id
                  ? "memory.html?case=" + encodeURIComponent(item.case_id)
                  : "personal.html?tab=notifications";
              };
            } catch {}
          }
        }
        if (!current && document.visibilityState === "visible") show(item);
      }
      window.dispatchEvent(new CustomEvent("reminder-inbox", { detail: rows }));
    } catch {
      document.body.dataset.reminderConnection = "unavailable";
    } finally {
      busy = false;
    }
  }
  document.addEventListener("DOMContentLoaded", () => {
    poll();
    setInterval(poll, 5000);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });
  window.ZhimaiReminders = {
    refresh: poll,
    preview: (item) => {
      if (!item?.is_demo) return;
      document.getElementById("reminderAlert")?.remove();
      current = null;
      show(item, true);
    },
    test: () =>
      show(
        {
          name: "提醒测试",
          message:
            "你能看到这条提示，说明当前页面可以显示站内提醒。实际任务以约定时间和后端执行结果为准。",
        },
        true,
      ),
    read: async (id) => {
      await api("notifications/" + encodeURIComponent(id) + "/read", "POST");
      if (current?.id === id) {
        document.getElementById("reminderAlert")?.remove();
        current = null;
      }
      await poll();
    },
  };
})();
