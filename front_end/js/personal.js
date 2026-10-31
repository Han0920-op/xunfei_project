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
    const d = new Date(value);
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
        ? "已允许桌面通知 · 请保持本页打开"
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
      return `<article class="personal-card message-card"><div class="card-top"><span class="card-symbol">${icon("leaf")}</span><span class="personal-badge ${x.weather?.status === "ok" ? "" : "muted-badge"}">${x.weather?.status === "ok" ? "天气已更新" : "天气暂不可用"}</span></div><h2>${esc(x.name)}</h2><p class="message-text">${esc(x.message)}</p><small class="card-meta">${esc(timeLabel(x.created_at))} · 北京时间</small><div class="card-actions"><a href="index.html" class="text-button">回到智麦继续复查 ${icon("arrow")}</a><button class="text-button subtle-danger" data-remove="${esc(x.id)}">删除消息</button></div></article>`;
    return `<article class="personal-card"><div class="card-top"><span class="card-symbol">${icon(medicine ? "book" : "clock")}</span><span class="personal-badge ${medicine ? "amber-badge" : x.enabled ? "" : "muted-badge"}">${medicine ? "登记待核对" : x.enabled ? "已启用" : "已暂停"}</span></div>${medicine ? `<h2>${esc(x.name)}</h2><p class="registration-number">${esc(x.number || "登记证号待补充")}</p>` : `<div class="task-clock">${esc(x.time)}<small>每天 · 北京时间</small></div><h2>${esc(x.name)}</h2><p class="task-location">${esc(x.location)} · 每天 ${esc(x.time)} · ${x.enabled ? "已启用" : "已暂停"}</p>`}<p class="personal-note">${esc(x.notes || (medicine ? "可以在编辑中补充成分、保质期或使用备注。" : "到时查天气，提醒你观察麦苗变化。"))}</p>${!medicine && x.enabled ? `<small class="card-meta">下次检查：${esc(timeLabel(x.next))}</small>` : ""}<div class="card-actions">${medicine ? `<a class="text-button card-chat" href="index.html?medicine=${encodeURIComponent(x.id)}">带着这瓶药问智麦 ${icon("arrow")}</a>` : ""}<div><button class="text-button" data-edit="${esc(x.id)}">编辑</button><button class="text-button subtle-danger" data-remove="${esc(x.id)}">删除</button></div></div></article>`;
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
    root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon(medicine ? "book" : "clock")}${medicine ? "手里的药，心里有数" : "约好时间，接着关心麦田"}</span><h1>${medicine ? "我的农药库" : "提醒"}</h1><p>${medicine ? "记下已有的农药，核对时少找一次包装。" : "每天看一眼天气，也看看麦苗有没有新变化。"}</p></div><button class="button primary" data-new>${icon("plus")}${medicine ? "新增农药" : "新增每日检查"}</button></div><p class="error" id="personalError" role="alert"></p>${medicine ? `<div class="personal-banner">${icon("leaf")}<p>保存你确认的药品资料，智麦可以在对话中按需读取。<small>存入农药库不代表适用，使用前仍需结合登记范围和实际问题核对。</small></p><a href="index.html">问智麦 ${icon("arrow")}</a></div><div class="personal-toolbar"><h2>我保存的农药 <span id="listCount"></span></h2><label class="personal-search">${icon("search")}<input id="medicineSearch" type="search" placeholder="搜索名称或登记证号" aria-label="搜索农药" value="${esc(query)}"></label></div>` : `<div class="reminder-tabs" role="group" aria-label="提醒内容"><button class="${tab === "tasks" ? "selected" : ""}" data-tab="tasks">定时天气检查</button><button class="${tab === "notifications" ? "selected" : ""}" data-tab="notifications">检查消息</button></div><div class="notification-strip">${icon("clock")}<div><strong>${esc(notificationStatus())}</strong><small>后端运行时执行检查；关闭网页后，可回来查看消息。</small></div><button class="button secondary" id="notify">开启本页桌面通知</button></div>`}<section id="personalList" aria-label="${medicine ? "农药列表" : tab === "tasks" ? "天气检查计划" : "检查消息"}"></section><details class="personal-footnote"><summary>资料保存与提醒说明</summary><p>药品和任务保存在服务端，通过当前浏览器的个人凭据访问，更换浏览器不会自动同步。天气任务需要电脑开机且后端运行；重启后补查一次错过的检查。桌面通知需要授权并保持本页打开，尚不支持关闭网页后的推送。</p></details>`;
    list();
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
    const fields = `<p class="form-intro">${task ? "约好时间，智麦会查询当天的天气，并记下你关心的变化。" : "照着包装填写即可，不清楚的资料可以稍后补充。"}</p><label>${task ? "提醒名称" : "农药名称"}<input name="name" required maxlength="100" placeholder="${task ? "例如：麦苗黄叶复查" : "例如：包装上的产品名称"}" value="${esc(item.name || (task ? "每日麦苗检查" : ""))}"></label>${task ? `<div class="personal-form-row"><label>城市或市县编码<input name="location" required maxlength="80" placeholder="例如：郑州" value="${esc(item.location || "")}"></label><label>每天执行时间<input name="time" type="time" required value="${esc(item.time || "08:00")}"></label></div><label>状态<select name="enabled"><option value="true">启用</option><option value="false" ${item.enabled === false ? "selected" : ""}>暂停</option></select></label>` : `<label>登记证号 <small>选填，不清楚可暂留空</small><input name="number" maxlength="30" placeholder="例如：PD20250010" value="${esc(item.number || "")}"></label>`}<label>${task ? "到时提醒我检查什么" : "成分、有效期及其他备注"}<textarea name="notes" rows="3" maxlength="500" placeholder="${task ? "例如：看看之前发黄的麦苗，补拍新叶和叶背" : "可记录有效成分、包装标注的保质期等"}">${esc(item.notes || "")}</textarea></label><p class="dialog-note">${task ? "按北京时间执行。仅做天气查询与检查提醒，不会自动安排施药。" : "这些是你的个人资料，登记适用范围仍需另外核对。"}</p>`;
    U.modal(
      item.id
        ? "编辑" + (task ? "提醒" : "农药")
        : task
          ? "新增每日检查"
          : "新增农药",
      fields,
      async (data) => {
        const body = Object.fromEntries(data);
        if (task) body.enabled = body.enabled === "true";
        await api(tab + "/" + identifier, "PUT", body);
        U.close();
        U.toast(
          "已保存" + (task ? "，每日检查时间已更新。" : "到我的农药库。"),
        );
        await render();
      },
      task ? "确认保存并设置每日检查" : "确认保存",
    );
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
      if (b.id === "notify") {
        if (!("Notification" in window))
          throw Error("当前浏览器不支持桌面通知，请查看检查消息。");
        await Notification.requestPermission();
        U.toast(notificationStatus());
        await render();
      }
    } catch (e) {
      fail(e);
    }
  });
  root.innerHTML =
    '<div class="personal-loading" role="status">正在读取你的资料…</div>';
  try {
    await api("session");
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
  let initialized = false,
    seen = new Set();
  async function poll() {
    try {
      const rows = await api("notifications");
      let changed = false;
      for (const x of rows) {
        if (!seen.has(x.id)) {
          changed = true;
          if (
            initialized &&
            "Notification" in window &&
            Notification.permission === "granted"
          )
            new Notification(x.name, { body: x.message, tag: x.id });
        }
        seen.add(x.id);
      }
      if (
        initialized &&
        changed &&
        tab === "notifications" &&
        !document.getElementById("dialog").open
      )
        await render();
      initialized = true;
    } catch {}
  }
  await poll();
  setInterval(poll, 15000);
})();
