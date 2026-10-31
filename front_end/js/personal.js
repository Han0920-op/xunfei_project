/* Personal workspace. Existing API and ownership remain unchanged. */
(async () => {
  const U = window.FarmerUI,
    { esc, icon } = U;
  const params = new URLSearchParams(location.search);
  let tab = ["tasks", "notifications"].includes(params.get("tab"))
    ? params.get("tab")
    : "medicines";
  const medicine = tab === "medicines";
  document.getElementById("app").innerHTML = AppShell.markup(
    medicine ? "medicines" : "reminders",
  );
  const root = document.getElementById("main");
  root.classList.add("personal-main");
  let entries = [],
    query = "",
    revision = 0;
  const timeLabel = (value) => {
    const d = new Date(
      typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)
        ? value + "+08:00"
        : value,
    );
    return isNaN(d)
      ? "时间待确认"
      : new Intl.DateTimeFormat("zh-CN", {
          timeZone: "Asia/Shanghai",
          month: "long",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }).format(d);
  };
  async function api(path, method = "GET", body) {
    const r = await fetch("/api/personal/" + path, {
      method,
      headers: { "Content-Type": "application/json", "X-Zhimai-Personal": "1" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) {
      let e = await r.json();
      throw Error(
        typeof e.detail === "string"
          ? e.detail
          : "资料未能保存，请检查填写内容。",
      );
    }
    return r.json();
  }
  function fail(e) {
    const el = document.getElementById("personalError");
    if (el) el.textContent = e.message;
    else
      root.innerHTML = `<p class="error" role="alert">${esc(e.message)}</p><button class="button secondary" id="reload">重新加载</button>`;
    document
      .getElementById("reload")
      ?.addEventListener("click", () => render().catch(fail));
  }
  function notificationStatus() {
    return !("Notification" in window)
      ? "当前浏览器不支持桌面通知"
      : Notification.permission === "granted"
        ? "已允许桌面通知 · 请保持智麦页面打开"
        : Notification.permission === "denied"
          ? "通知未获授权 · 结果仍保存到检查消息"
          : "可开启桌面通知 · 网页打开时提醒";
  }
  function empty() {
    const search = Boolean(query);
    return `<div class="personal-empty"><div class="empty-illustration">${icon(search ? "search" : medicine ? "book" : tab === "tasks" ? "clock" : "leaf")}</div><h2>${search ? "没有找到这瓶药" : medicine ? "把手里的药，放心记在这里" : tab === "tasks" ? "给麦苗的变化，留一个提醒" : "检查消息，会在这里等你"}</h2><p>${search ? "试试药品名称或登记证号。" : medicine ? "先添加一瓶农药。下次问智麦时，\n就能结合你手里的药继续核对。" : tab === "tasks" ? "约好每天的时间，查查天气，\n也记得回头看看麦苗的变化。" : "任务执行后，天气和检查提示会保存在这里。\n没查到天气，也会如实告诉你。"}</p>${!search && tab !== "notifications" ? `<button class="button primary" data-new>${icon("plus")}${medicine ? "添加第一瓶农药" : "设置第一个提醒"}</button>` : ""}</div>`;
  }
  function card(x) {
    if (tab === "notifications")
      return `<article class="personal-card message-card"><div class="card-top"><span class="card-symbol">${icon("leaf")}</span><span class="personal-badge ${x.weather?.status === "ok" ? "" : "muted-badge"}">${x.task_type === "reminder" ? "提醒已到时间" : x.weather?.status === "ok" ? "天气已更新" : "天气暂不可用"}</span></div><h2>${esc(x.name)}</h2><p class="message-text">${esc(x.message)}</p><small class="card-meta">${esc(timeLabel(x.created_at))} · 北京时间</small><div class="card-actions"><a href="index.html" class="text-button">回到智麦继续复查 ${icon("arrow")}</a>${!x.read ? `<button class="text-button" data-read="${esc(x.id)}">标为已读</button>` : `<small>已读</small>`}<button class="text-button subtle-danger" data-remove="${esc(x.id)}">删除消息</button></div></article>`;
    return `<article class="personal-card"><div class="card-top"><span class="card-symbol">${icon(medicine ? "book" : "clock")}</span><span class="personal-badge ${medicine ? "amber-badge" : x.enabled ? "" : "muted-badge"}">${medicine ? "登记待核对" : x._completed_at ? "已提醒" : x.enabled ? "已启用" : "已暂停"}</span></div>${medicine ? `<h2>${esc(x.name)}</h2><p class="registration-number">${esc(x.number || "登记证号待补充")}</p>` : `<div class="task-clock">${esc(x.recurrence === "once" ? timeLabel(x.run_at) : x.time)}<small>${x.recurrence === "once" ? "仅一次" : "每天"} · 北京时间</small></div><h2>${esc(x.name)}</h2><p class="task-location">${esc(x.task_type === "reminder" ? "普通提醒" : x.location)} · ${x.recurrence === "once" ? "仅一次" : "每天 " + esc(x.time)} · ${x._completed_at ? "已提醒" : x.enabled ? "已启用" : "已暂停"}</p>`}<p class="personal-note">${esc(x.notes || (medicine ? "可以在编辑中补充成分、保质期或使用备注。" : "到时查天气，提醒你观察麦苗变化。"))}</p>${!medicine && x.enabled ? `<small class="card-meta">下次检查：${esc(timeLabel(x.next))}</small>` : ""}<div class="card-actions">${medicine ? `<a class="text-button card-chat" href="index.html?medicine=${encodeURIComponent(x.id)}">带着这瓶药问智麦 ${icon("arrow")}</a>` : ""}<div><button class="text-button" data-edit="${esc(x.id)}">编辑</button><button class="text-button subtle-danger" data-remove="${esc(x.id)}">删除</button></div></div></article>`;
  }
  function list() {
    const data = entries.filter(
      (x) =>
        !query ||
        [x.name, x.number, x.notes].some((v) =>
          String(v || "")
            .toLowerCase()
            .includes(query.toLowerCase()),
        ),
    );
    document.getElementById("personalList").innerHTML = data.length
      ? `<div class="personal-grid">${data.map(card).join("")}</div>`
      : empty();
    const count = document.getElementById("listCount");
    if (count) count.textContent = `${data.length} 瓶`;
  }
  async function render() {
    const version = ++revision;
    const items = await api(tab);
    if (version !== revision) return;
    entries = items;
    document.title = (medicine ? "我的农药库" : "提醒") + " · 智麦";
    root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon(medicine ? "book" : "clock")}${medicine ? "手里的药，心里有数" : "约好时间，接着关心麦田"}</span><h1>${medicine ? "我的农药库" : "提醒"}</h1><p>${medicine ? "记下已有的农药，核对时少找一次包装。" : "普通提醒、复查事项和天气检查，约好时间自动提示。"}</p></div><button class="button primary" data-new>${icon("plus")}${medicine ? "新增农药" : "新增提醒"}</button></div><p class="error" id="personalError" role="alert"></p>${medicine ? `<div class="personal-banner">${icon("leaf")}<p>保存你确认的药品资料，智麦可以在对话中按需读取。<small>存入农药库不代表适用，使用前仍需结合登记范围和实际问题核对。</small></p><a href="index.html">问智麦 ${icon("arrow")}</a></div><div class="personal-toolbar"><h2>我保存的农药 <span id="listCount"></span></h2><label class="personal-search">${icon("search")}<input id="medicineSearch" type="search" placeholder="搜索名称或登记证号" aria-label="搜索农药" value="${esc(query)}"></label></div>` : `<div class="reminder-tabs" role="group" aria-label="提醒内容"><button class="${tab === "tasks" ? "selected" : ""}" data-tab="tasks">提醒计划</button><button class="${tab === "notifications" ? "selected" : ""}" data-tab="notifications">检查消息</button></div><div class="notification-strip">${icon("clock")}<div><strong>${esc(notificationStatus())}</strong><small>智麦任意页面到点会弹出站内提醒；后端需保持运行。</small></div><button class="button secondary" id="notify">开启桌面通知</button><button class="button secondary" id="testReminder">测试提醒</button></div>`}<section id="personalList" aria-label="${medicine ? "农药列表" : tab === "tasks" ? "天气检查计划" : "检查消息"}"></section><details class="personal-footnote"><summary>资料保存与提醒说明</summary><p>药品和任务保存在服务端，通过当前浏览器的个人凭据访问，更换浏览器不会自动同步。天气任务需要电脑开机且后端运行；重启后补查一次错过的检查。桌面通知需要授权并保持本页打开，尚不支持关闭网页后的推送。</p></details>`;
    list();
    if (!medicine) {
      const strip = document.querySelector(".notification-strip");
      const state = document.createElement("p");
      state.id = "schedulerStatus";
      state.className = "dialog-note";
      strip.after(state);
      api("status")
        .then((result) => {
          if (state.isConnected)
            state.textContent = result.scheduler_running
              ? "后台检查正常运行 · 北京时间 · 到点执行并提示"
              : "后台调度尚未就绪或已停止，请重启后端；仅保存任务不会触发提醒。";
        })
        .catch(() => {
          if (state.isConnected)
            state.textContent = "暂时无法确认后台状态，请检查后端连接。";
        });
    }
    document
      .getElementById("medicineSearch")
      ?.addEventListener("input", (e) => {
        query = e.target.value;
        list();
      });
  }
  function edit(item = {}) {
    const identifier = item.id || crypto.randomUUID(),
      task = !medicine;
    const defaultDate = new Date(Date.now() + 300000)
      .toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" })
      .replace(" ", "T")
      .slice(0, 16);
    const fields = `<p class="form-intro">${task ? "普通提醒无需地点；选择天气检查时，到点会另外查询天气。" : "照着包装填写，不清楚的内容可稍后补充。"}</p>
      <label>${task ? "提醒名称" : "农药名称"}<input name="name" required maxlength="100" value="${esc(item.name || (task ? "麦苗复查提醒" : ""))}"></label>
      ${
        task
          ? `<label>提醒类型<select name="task_type"><option value="reminder">普通提醒</option><option value="weather" ${item.task_type === "weather" ? "selected" : ""}>天气检查</option></select></label>
      <label>重复方式<select name="recurrence"><option value="once">仅提醒一次</option><option value="daily" ${item.recurrence === "daily" ? "selected" : ""}>每天重复</option></select></label>
      <label data-weather-field>城市或市县编码<input name="location" maxlength="80" placeholder="例如：郑州" value="${esc(item.location || "")}"></label>
      <label data-daily-field>每天执行时间（北京时间）<input name="time" type="time" value="${esc(item.time || "08:00")}"></label>
      <label data-once-field>提醒日期与时间（北京时间）<input name="run_at" type="datetime-local" value="${esc(item.run_at ? new Date(item.run_at.includes("+") || item.run_at.endsWith("Z") ? item.run_at : item.run_at + "+08:00").toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).replace(" ", "T").slice(0, 16) : defaultDate)}"></label>
      <label>状态<select name="enabled"><option value="true">启用</option><option value="false" ${item.enabled === false ? "selected" : ""}>暂停</option></select></label>`
          : `<label>登记证号（选填）<input name="number" maxlength="30" value="${esc(item.number || "")}"></label>`
      }
      <label>${task ? "提醒内容" : "成分、有效期及其他备注"}<textarea name="notes" rows="3" maxlength="500" placeholder="${task ? "例如：看看之前发黄的麦苗，补拍近景" : ""}">${esc(item.notes || "")}</textarea></label>
      <p class="dialog-note">${task ? "按北京时间执行。智麦页面打开时会显示站内提醒，桌面通知需要授权；电脑与后端需保持运行。" : "保存不等于适用，请核对登记范围。"}</p>`;
    const modal = U.modal(
      item.id
        ? "编辑" + (task ? "提醒" : "农药")
        : task
          ? "新增提醒"
          : "新增农药",
      fields,
      async (data) => {
        const body = Object.fromEntries(data);
        if (task) body.enabled = body.enabled === "true";
        const result = await api(
          (task ? "tasks" : "medicines") + "/" + identifier,
          "PUT",
          body,
        );
        U.close();
        U.toast(
          task
            ? "已设置提醒，下次执行：" + timeLabel(result.next)
            : "已保存到我的农药库。",
        );
        await render();
        window.ZhimaiReminders?.refresh();
      },
      task ? "确认设置提醒" : "确认保存",
    );
    if (task) {
      const form = modal.querySelector("form");
      const sync = () => {
        const daily = form.elements.recurrence.value === "daily",
          weather = form.elements.task_type.value === "weather";
        for (const [selector, on] of [
          ["[data-weather-field]", weather],
          ["[data-daily-field]", daily],
          ["[data-once-field]", !daily],
        ]) {
          const label = form.querySelector(selector);
          label.hidden = !on;
          const input = label.querySelector("input");
          input.disabled = !on;
          input.required = on;
        }
      };
      form.elements.task_type.addEventListener("change", sync);
      form.elements.recurrence.addEventListener("change", sync);
      sync();
    }
  }
  root.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.hasAttribute("data-new")) edit();
      if (b.dataset.tab) {
        tab = b.dataset.tab;
        query = "";
        history.replaceState(null, "", "personal.html?tab=" + tab);
        await render();
      }
      if (b.dataset.edit) edit(entries.find((x) => x.id === b.dataset.edit));
      if (b.dataset.remove) {
        const id = b.dataset.remove;
        U.modal(
          "删除" +
            (medicine ? "这瓶农药" : tab === "tasks" ? "这个提醒" : "这条消息"),
          "<p>删除后将不再显示在这里。" +
            (tab === "tasks" ? "此计划也会停止执行。" : "") +
            "</p>",
          async () => {
            await api(tab + "/" + encodeURIComponent(id), "DELETE");
            U.close();
            await render();
            U.toast("已删除。");
          },
          "确认删除",
        );
      }
      if (b.id === "testReminder") window.ZhimaiReminders?.test();
      if (b.dataset.read) {
        await window.ZhimaiReminders.read(b.dataset.read);
        await render();
      }
      if (b.id === "notify") {
        if (!("Notification" in window))
          throw Error("当前浏览器不支持桌面通知，请查看检查消息。");
        await Notification.requestPermission();
        U.toast(
          Notification.permission === "denied"
            ? "浏览器已屏蔽桌面通知，可在地址栏的网站权限中允许；站内提醒仍可用。"
            : notificationStatus(),
        );
        await render();
      }
    } catch (e) {
      fail(e);
    }
  });
  root.innerHTML =
    '<div class="personal-loading" role="status">正在读取你的资料…</div>';
  try {
    await window.PersonalReady;
    await render();
    if (!medicine && tab === "tasks" && params.has("location"))
      edit({
        id: params.get("draft") || undefined,
        location: params.get("location"),
        time: params.get("time") || "08:00",
        notes: params.get("concern") || "",
      });
  } catch (e) {
    fail(e);
  }
  window.addEventListener("reminder-inbox", () => {
    if (!medicine && !document.getElementById("dialog").open)
      render().catch(fail);
  });
})();
