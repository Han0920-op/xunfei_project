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
    filter = "all",
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
  function artwork() {
    return `<div class="workspace-art" aria-hidden="true"><svg viewBox="0 0 300 210" fill="none"><circle cx="164" cy="104" r="88" fill="#ffffff" opacity=".05"/><circle cx="164" cy="104" r="65" stroke="#c8d9b4" stroke-dasharray="3 8" opacity=".3"/><path d="M24 180Q150 155 278 180" stroke="#a7bd91" opacity=".4"/>${medicine ? `<g class="art-float"><rect x="102" y="40" width="62" height="24" rx="6" fill="#d5dfba"/><path d="M110 64H156V78Q177 86 177 105V166Q177 176 166 176H100Q89 176 89 166V105Q89 86 110 78Z" fill="#f5f1df"/><rect x="89" y="111" width="88" height="46" fill="#8fa577"/><path d="M133 146V121M133 136Q113 134 117 121Q131 122 133 136ZM133 132Q152 129 149 117Q135 119 133 132Z" stroke="#f7f5e9" stroke-width="2"/><rect x="187" y="108" width="45" height="67" rx="8" fill="#d3b87c"/><rect x="193" y="97" width="33" height="15" rx="4" fill="#b8c7a2"/><path d="M198 140H222M198 147H215" stroke="#fff6df" stroke-width="3"/></g>` : `<g class="art-float"><rect x="76" y="51" width="154" height="126" rx="14" fill="#f4f0df"/><path d="M76 66Q76 51 90 51H216Q230 51 230 66V86H76Z" fill="#b5c596"/><path d="M111 43V62M195 43V62" stroke="#ecdfb8" stroke-width="8" stroke-linecap="round"/><path d="M99 106H117M134 106H152M169 106H187M99 129H117M134 129H152M99 152H117" stroke="#bcc6a6" stroke-width="6" stroke-linecap="round"/><circle cx="209" cy="153" r="34" fill="#d7bd80" stroke="#254f3d" stroke-width="5"/><path d="M209 134V153L222 160" stroke="#254f3d" stroke-width="3" stroke-linecap="round"/></g>`}<path class="art-sprig" d="M46 177Q60 136 46 100M51 140Q29 137 28 121Q48 122 51 140ZM52 125Q72 119 69 103Q53 106 52 125Z" stroke="#adc199" stroke-width="2"/></svg></div>`;
  }
  function overview() {
    const metrics = medicine
      ? [
          [entries.length, "已保存资料"],
          [entries.filter((x) => x.number).length, "已填写登记号"],
          [entries.filter((x) => !x.number).length, "待补登记号"],
        ]
      : tab === "tasks"
        ? [
            [
              entries.filter((x) => x.enabled && !x._completed_at).length,
              "启用中",
            ],
            [entries.filter((x) => x._completed_at).length, "已提醒"],
            [
              entries.filter((x) => !x.enabled && !x._completed_at).length,
              "已暂停",
            ],
          ]
        : [
            [entries.length, "全部消息"],
            [entries.filter((x) => !x.read).length, "未读消息"],
            [entries.filter((x) => x.read).length, "已读消息"],
          ];
    return metrics
      .map(
        ([value, label], i) =>
          `<div class="workspace-metric"><span class="metric-mark">${icon(i === 0 ? (medicine ? "book" : "clock") : i === 1 ? "check" : "more")}</span><div><strong>${value}</strong><span>${label}</span></div></div>`,
      )
      .join("");
  }
  function filters() {
    const options = medicine
      ? [
          ["all", "全部农药"],
          ["missing", "待补登记号"],
          ["noted", "有备注"],
        ]
      : tab === "tasks"
        ? [
            ["all", "全部计划"],
            ["active", "启用中"],
            ["completed", "已提醒"],
            ["paused", "已暂停"],
          ]
        : [
            ["all", "全部消息"],
            ["unread", "未读"],
            ["read", "已读"],
          ];
    return options
      .map(
        ([key, label]) =>
          `<button type="button" data-filter="${key}" aria-pressed="${filter === key}">${label}</button>`,
      )
      .join("");
  }
  function matchesFilter(x) {
    return (
      filter === "all" ||
      (filter === "missing" && !x.number) ||
      (filter === "noted" && Boolean(x.notes)) ||
      (filter === "active" && x.enabled && !x._completed_at) ||
      (filter === "completed" && Boolean(x._completed_at)) ||
      (filter === "paused" && !x.enabled && !x._completed_at) ||
      (filter === "unread" && !x.read) ||
      (filter === "read" && x.read)
    );
  }
  function empty() {
    if (filter !== "all" && !query)
      return `<div class="personal-empty"><div class="empty-illustration">${icon("check")}</div><h2>这个分类暂时没有内容</h2><p>可以切换到全部，查看已保存的${medicine ? "农药资料" : tab === "tasks" ? "提醒计划" : "检查消息"}。</p><button class="button secondary" data-filter="all">查看全部</button></div>`;
    const search = Boolean(query);
    return `<div class="personal-empty"><div class="empty-illustration">${icon(search ? "search" : medicine ? "book" : tab === "tasks" ? "clock" : "leaf")}</div><h2>${search ? "没有找到这瓶药" : medicine ? "把手里的药，放心记在这里" : tab === "tasks" ? "给麦苗的变化，留一个提醒" : "检查消息，会在这里等你"}</h2><p>${search ? "试试药品名称或登记证号。" : medicine ? "先添加一瓶农药。下次问智麦时，\n就能结合你手里的药继续核对。" : tab === "tasks" ? "约好每天的时间，查查天气，\n也记得回头看看麦苗的变化。" : "任务执行后，天气和检查提示会保存在这里。\n没查到天气，也会如实告诉你。"}</p>${!search && tab !== "notifications" ? `<button class="button primary" data-new>${icon("plus")}${medicine ? "添加第一瓶农药" : "设置第一个提醒"}</button>` : ""}</div>`;
  }
  function weatherLabel(x) {
    if (x.superseded) return "历史预警 · 已有更新";
    if (x.warning?.status === "cancelled") return "预警已解除";
    if (Date.parse(x.warning?.expires_at) <= Date.now())
      return "历史预警 · 已过期";
    return "天气预警";
  }
  function card(x) {
    if (tab === "notifications")
      return `<article class="personal-card message-card ${x.read ? "is-read" : "is-unread"}"><div class="card-top"><span class="card-symbol">${icon("leaf")}</span><span class="personal-badge ${x.weather?.status === "ok" ? "" : "muted-badge"}">${x.task_type === "weather_alert" ? weatherLabel(x) : x.task_type === "regional" ? "区域巡查提示" : x.task_type === "followup" ? "案例复查到时" : x.task_type === "reminder" ? "提醒已到时间" : x.weather?.status === "ok" ? "天气已更新" : "天气暂不可用"}</span></div><h2>${esc(x.name)}</h2><p class="message-text">${esc(x.message)}</p>${x.task_type === "weather_alert" ? `<p class="personal-note">${esc(x.warning?.publisher || "")} · 发布 ${esc(timeLabel(x.warning?.issued_at))} · 有效至 ${esc(timeLabel(x.warning?.expires_at))}</p><ul>${(x.advice || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul><a class="text-button" href="weather-alerts.html">查看天气防护建议</a>` : ""}${x.source ? `<p class="personal-note">来源：${esc(x.source.title)} · ${esc(x.source.published_on)} · 适用：${esc((x.source.regions || []).join("、"))}</p>` : ""}<small class="card-meta">${esc(timeLabel(x.created_at))} · 北京时间</small><div class="card-actions"><a href="${x.case_id ? "memory.html?case=" + encodeURIComponent(x.case_id) : "index.html"}" class="text-button">回到智麦继续复查 ${icon("arrow")}</a>${!x.read ? `<button class="text-button" data-read="${esc(x.id)}">标为已读</button>` : `<small>已读</small>`}<button class="text-button subtle-danger" data-remove="${esc(x.id)}">删除消息</button></div></article>`;
    return `<article class="personal-card ${medicine ? "medicine-card" : "schedule-card"} ${!medicine && !x.enabled ? "is-paused" : ""}"><div class="card-top"><span class="card-symbol">${icon(medicine ? "book" : "clock")}</span><span class="personal-badge ${medicine ? "amber-badge" : x.enabled ? "" : "muted-badge"}">${medicine ? "已保存 · 登记待核对" : x._completed_at ? "已提醒" : x.enabled ? "已启用" : "已暂停"}</span></div>${medicine ? `<h2>${esc(x.name)}</h2><p class="registration-number"><span>登记证号</span>${esc(x.number || "待补充")}</p>` : `<div class="task-clock">${esc(x.recurrence === "once" ? timeLabel(x.run_at) : x.time)}<small>${x.recurrence === "once" ? "仅一次" : "每天"} · 北京时间</small></div><h2>${esc(x.name)}</h2><p class="task-location">${esc(x.task_type === "followup" ? "案例复查" : x.task_type === "reminder" ? "普通提醒" : x.location)} · ${x.recurrence === "once" ? "仅一次" : "每天 " + esc(x.time)} · ${x._completed_at ? "已提醒" : x.enabled ? "已启用" : "已暂停"}</p>`}<p class="personal-note">${esc(x.notes || (medicine ? "可以在编辑中补充成分、保质期或使用备注。" : x.task_type === "weather" ? "到时查询天气，留意田间变化。" : "按约定时间提醒你，接着观察田间变化。"))}</p>${!medicine && x.enabled ? `<small class="card-meta">下次检查：${esc(timeLabel(x.next))}</small>` : ""}<div class="card-actions">${x.case_id ? `<a href="memory.html?case=${encodeURIComponent(x.case_id)}">查看关联案例</a>` : ""}${medicine ? `<a class="text-button card-chat" href="index.html?medicine=${encodeURIComponent(x.id)}">带着这瓶药问智麦 ${icon("arrow")}</a>` : ""}<div><button class="text-button" data-edit="${esc(x.id)}">编辑</button><button class="text-button subtle-danger" data-remove="${esc(x.id)}">删除</button></div></div></article>`;
  }
  function list() {
    const data = entries.filter(
      (x) =>
        matchesFilter(x) &&
        (!query ||
          [x.name, x.number, x.notes].some((v) =>
            String(v || "")
              .toLowerCase()
              .includes(query.toLowerCase()),
          )),
    );
    document.getElementById("personalList").innerHTML = data.length
      ? `<div class="personal-grid">${data.map(card).join("")}</div>`
      : empty();
    const count = document.getElementById("listCount");
    if (count)
      count.textContent = `${data.length} ${medicine ? "条资料" : "条"}`;
    const metrics = document.getElementById("workspaceMetrics");
    if (metrics) metrics.innerHTML = overview();
    const choices = document.getElementById("workspaceFilters");
    if (choices) choices.innerHTML = filters();
  }
  async function render() {
    const version = ++revision;
    const items = await api(tab);
    if (version !== revision) return;
    entries = items;
    document.title = (medicine ? "我的农药库" : "提醒任务") + " · 智麦";
    root.innerHTML = `${medicine ? "" : AppShell.alertBreadcrumb("提醒任务")}
      <header class="workspace-hero"><div class="workspace-hero-copy"><span class="page-eyebrow">${icon(medicine ? "book" : "clock")}${medicine ? "手里的药，心里有数" : "把牵挂，交给时间"}</span><h1>${medicine ? "我的农药库" : "提醒任务"}</h1><p>${medicine ? "收好每一份药品资料，\n让下一次核对更从容。" : "田间的每一次变化，\n都值得按时回头看看。"}</p><button class="button primary" data-new>${icon("plus")}${medicine ? "新增农药" : "新增提醒"}</button></div>${artwork()}</header>
      <div class="workspace-metrics" id="workspaceMetrics" aria-label="${medicine ? "农药资料概览" : "提醒概览"}"></div>
      <p class="error" id="personalError" role="alert"></p>
      <div class="workspace-columns"><div class="workspace-content">
      ${medicine ? "" : `<div class="reminder-tabs" role="group" aria-label="提醒内容"><button class="${tab === "tasks" ? "selected" : ""}" aria-pressed="${tab === "tasks"}" data-tab="tasks">${icon("clock")}提醒计划</button><button class="${tab === "notifications" ? "selected" : ""}" aria-pressed="${tab === "notifications"}" data-tab="notifications">${icon("history")}检查消息</button></div>`}
      <div class="personal-toolbar"><h2>${medicine ? "我保存的农药" : tab === "tasks" ? "我的提醒计划" : "收到的检查消息"} <span id="listCount"></span></h2>${medicine ? `<label class="personal-search">${icon("search")}<input id="medicineSearch" type="search" placeholder="搜索名称或登记证号" aria-label="搜索农药" value="${esc(query)}"></label>` : ""}</div>
      <div class="workspace-filters" id="workspaceFilters" role="group" aria-label="筛选${medicine ? "农药" : "提醒"}"></div>
      <section id="personalList" aria-label="${medicine ? "农药列表" : tab === "tasks" ? "天气检查计划" : "检查消息"}"></section>
      </div><aside class="workspace-aside" aria-label="${medicine ? "农药资料使用提示" : "提醒设置与快捷入口"}">
      ${medicine ? `<div class="workspace-guide"><span class="guide-icon">${icon("leaf")}</span><h2>从保存，到安心核对</h2><ol><li><strong>照着包装记下来</strong><p>名称、登记号和备注，随时补充。</p></li><li><strong>带着资料问智麦</strong><p>对话中按需读取，少找一次包装。</p></li><li><strong>用前再核对</strong><p>确认登记范围，结合田间问题判断。</p></li></ol><a class="button secondary" href="index.html">问智麦 ${icon("arrow")}</a></div><div class="workspace-tip"><strong>已保存，不等于已核实</strong><p>“登记待核对”不影响入库，表示当前登记有效状态和用途尚未核实。</p></div>` : `<div class="notification-strip"><span class="guide-icon">${icon("clock")}</span><h2>让提醒准时抵达</h2><div><strong>${esc(notificationStatus())}</strong><small>智麦任意页面到点会弹出站内提醒；电脑与后端需保持运行。</small></div><button class="button secondary" id="notify">开启桌面通知</button><button class="text-button" id="testReminder">测试提醒 ${icon("arrow")}</button></div><div class="workspace-guide workspace-shortcuts"><h2>也关心田外的变化</h2><a href="weather-alerts.html">${icon("leaf")}天气预警 ${icon("arrow")}</a><a href="intelligence.html?view=bulletins">${icon("book")}植保资讯 ${icon("arrow")}</a><a href="intelligence.html">${icon("plus")}管理地区订阅 ${icon("arrow")}</a></div>`}
      </aside></div><details class="personal-footnote"><summary>资料保存与提醒说明</summary><p>药品和任务保存在服务端，通过当前浏览器的个人凭据访问，更换浏览器不会自动同步。天气任务需要电脑开机且后端运行；重启后补查一次错过的检查。桌面通知需要授权并保持网页打开，尚不支持关闭网页后的推送。</p></details>`;
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
  async function edit(item = {}) {
    let cases = [];
    if (!medicine) {
      await window.PersonalReady;
      const r = await fetch("/api/memory/cases", { cache: "no-store" });
      if (r.ok) cases = (await r.json()).filter((c) => !c.archived);
      if (
        !item.id &&
        params.get("case") &&
        !cases.some((c) => c.id === params.get("case"))
      )
        throw Error(
          "关联案例已结束或暂时无法读取，请先打开有效案例再安排复查。",
        );
    }
    if (!item.id && params.get("case"))
      item = {
        ...item,
        case_id: params.get("case"),
        task_type: "followup",
        recurrence: "once",
        ...(params.get("compose") === "followup"
          ? {
              name: "案例复查",
              notes: "请按排查方案补拍关键部位，并记录与上次相比的变化。",
            }
          : {}),
      };

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
          ? `<label>提醒类型<select name="task_type"><option value="reminder">普通提醒</option><option value="followup" ${item.task_type === "followup" ? "selected" : ""}>案例复查</option><option value="weather" ${item.task_type === "weather" ? "selected" : ""}>天气检查</option></select></label>
      <label>关联案例（普通提醒可不选）<select name="case_id"><option value="">不关联案例</option>${cases.map((c) => `<option value="${esc(c.id)}" ${item.case_id === c.id ? "selected" : ""}>${esc(c.title)}</option>`).join("")}</select></label>
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
        const followup = form.elements.task_type.value === "followup";
        form.elements.case_id.required = followup;
        if (followup) form.elements.recurrence.value = "once";
        form.elements.recurrence.querySelector("[value=daily]").disabled =
          followup;
        const showDaily = form.elements.recurrence.value === "daily";
        for (const [selector, on] of [
          ["[data-weather-field]", weather],
          ["[data-daily-field]", showDaily],
          ["[data-once-field]", !showDaily],
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
      if (b.hasAttribute("data-new")) await edit();
      if (b.dataset.filter) {
        filter = b.dataset.filter;
        list();
        document
          .querySelector(`#workspaceFilters [data-filter="${filter}"]`)
          ?.focus();
      }
      if (b.dataset.tab) {
        filter = "all";
        tab = b.dataset.tab;
        query = "";
        window.ChatNavigation.replace("personal.html?tab=" + tab);
        await render();
      }
      if (b.dataset.edit)
        await edit(entries.find((x) => x.id === b.dataset.edit));
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
      await edit({
        id: params.get("draft") || undefined,
        location: params.get("location"),
        time: params.get("time") || "08:00",
        notes: params.get("concern") || "",
      });
    else if (
      !medicine &&
      tab === "tasks" &&
      params.get("compose") === "followup" &&
      params.get("case")
    )
      await edit();
  } catch (e) {
    fail(e);
  }
  async function refreshMedicines() {
    if (
      !medicine ||
      !document.getElementById("personalList") ||
      document.getElementById("dialog")?.open
    )
      return;
    const version = ++revision;
    const items = await api("medicines");
    if (version !== revision || document.getElementById("dialog")?.open) return;
    entries = items;
    list();
  }
  window.addEventListener("storage", (event) => {
    if (event.key === "zhimai:medicines-updated")
      refreshMedicines().catch(fail);
  });
  window.addEventListener("focus", () => refreshMedicines().catch(fail));
  window.addEventListener("zhimai:resume", () =>
    refreshMedicines().catch(fail),
  );
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshMedicines().catch(fail);
  });
  window.addEventListener("reminder-inbox", () => {
    if (!medicine && !document.getElementById("dialog").open)
      render().catch(fail);
  });
})();
