(async () => {
  const { esc, icon, modal, close, toast } = FarmerUI;
  document.getElementById("app").innerHTML = AppShell.markup("reminders");
  const root = document.getElementById("main");
  root.classList.add("personal-main");
  let data;
  async function api(path, method = "GET", body) {
    await window.PersonalReady;
    const r = await fetch("/api/intelligence/" + path, {
      method,
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Zhimai-Personal": "1" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const d = await r.json();
    if (!r.ok)
      throw Error(typeof d.detail === "string" ? d.detail : "订阅暂不可用");
    return d;
  }
  function error(e) {
    let el = document.getElementById("intelError");
    if (el) el.textContent = e.message;
    else root.textContent = e.message;
  }
  async function render() {
    const [settings, sources] = await Promise.all([
      api("subscriptions"),
      api("sources"),
    ]);
    data = settings;
    const active = sources.documents.filter(
      (d) => d.kind === "bulletin" && d.currently_applicable,
    );
    root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon("leaf")}来自官方公开情报，留意值得巡查的变化</span><h1>地区植保订阅</h1><p>选择你关心的地区与病虫害；有适用情报时，智麦提醒你回头看看。</p></div><button class="button primary" data-new>${icon("plus")}新增地区订阅</button></div><p class="error" id="intelError" role="alert"></p><div class="reminder-tabs"><a href="personal.html?tab=tasks">提醒计划</a><a href="personal.html?tab=notifications">检查消息</a><span class="selected">地区植保订阅</span></div>
  <div class="personal-banner">${icon("leaf")}<p>${active.length ? "有 " + active.length + " 条有效官方病虫情报，符合订阅条件后提示。" : "当前没有通过适用性核对的有效病虫情报，不会推送具体风险结论。"}<small>省级情报会标明省级范围，不能证明你的麦田已发病，也不能据此决定喷药。</small></p></div>
  <div class="personal-grid">${settings.subscriptions.map((s) => `<article class="personal-card"><span class="personal-badge ${s.enabled ? "" : "muted-badge"}">${s.enabled ? "订阅已开启" : "已暂停"}</span><h2>${esc(s.province)} ${esc(s.city)}</h2><p>${esc(s.pests.join("、"))}</p><p class="personal-note">每天最多 ${s.max_daily} 条；静默 ${esc(s.quiet_start)}—${esc(s.quiet_end)}（北京时间）。<br>同一情报仅提醒一次；过期情报不补发。</p><div class="card-actions"><button class="text-button" data-edit="${esc(s.id)}">编辑与暂停</button><button class="text-button" data-delete="${esc(s.id)}">取消订阅</button></div></article>`).join("") || '<section class="personal-empty"><h2>从一个关心的地区开始</h2><p>无需建地块档案；订阅后可随时暂停或取消。</p></section>'}</div>
  <h2 class="memory-section-title">官方来源与资料状态</h2><p class="personal-note">自动检查：${esc({ ok: "检查完成", unavailable: "来源暂不可用", partial_failure: "部分来源暂不可用", not_checked: "尚未检查" }[sources.status.state] || sources.status.state)} · ${esc(sources.status.checked_at || "等待后台首次检查")}<br>每4小时获取官方栏目，新增或变更内容先进入待核对；仅有效期内且地区、病虫害适用的情报参与通知。技术指导不会当成实时预警。</p>
  <div class="personal-grid">${sources.documents.map((d) => `<article class="personal-card"><span class="personal-badge muted-badge">${d.kind === "bulletin" ? "病虫情报" : d.kind === "guideline" ? "技术指导" : "待分类"} · ${d.currently_applicable ? "适用期内" : "待核对或已过期"}</span><h3>${esc(d.title)}</h3><p class="personal-note">发布：${esc(d.published_on)}<br>有效至：${esc(d.valid_until || "待核对")}<br>范围：${esc(d.regions.join("、") || "待核对")}<br>农技审校：待完成</p>${/^https:\/\/(www\.)?moa\.gov\.cn\//.test(d.url) ? `<a class="text-button" href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">官方原文 ${icon("arrow")}</a>` : ""}</article>`).join("") || '<p class="personal-note">尚未导入可核对的相关官方资料。不会使用模拟情报。</p>'}</div><details class="personal-footnote"><summary>通知与数据说明</summary><p>地区来自你的主动选择。天气检查需在提醒计划中单独设置；城市天气不能单独推导病虫发生风险。情报提醒通过站内消息和已授权的桌面通知送达，需后端运行；关闭网页后不支持浏览器推送，重新打开可查看未读消息。订阅未选定时，只展示公开资料。</p></details>`;
  }
  function edit(s = {}) {
    modal(
      s.id ? "编辑地区订阅" : "新增地区订阅",
      `<label>省级地区<select name="province">${data.provinces.map((p) => `<option ${s.province === p ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></label><label>城市（选填）<input name="city" maxlength="30" value="${esc(s.city || "")}" placeholder="例如郑州；省级情报仍保留省级范围"></label><fieldset class="subscription-pests"><legend>关心的病虫害（至少选一项）</legend>${data.pests.map((p) => `<label><input type="checkbox" name="pests" value="${esc(p)}" ${(s.pests || []).includes(p) ? "checked" : ""}>${esc(p)}</label>`).join("")}</fieldset><label>每天最多提醒<select name="max_daily">${[1, 2, 3].map((n) => `<option value="${n}" ${s.max_daily === n ? "selected" : ""}>${n} 条</option>`).join("")}</select></label><div class="case-detail-grid"><label>静默开始<input type="time" name="quiet_start" required value="${esc(s.quiet_start || "22:00")}"></label><label>静默结束<input type="time" name="quiet_end" required value="${esc(s.quiet_end || "07:00")}"></label></div><label>订阅状态<select name="enabled"><option value="true">开启订阅</option><option value="false" ${s.enabled === false ? "selected" : ""}>暂停订阅</option></select></label><p>你同意按这些条件接收区域巡查提示。静默开始与结束相同表示不设静默时间。</p>`,
      async (fd) => {
        const pests = fd.getAll("pests");
        if (!pests.length) throw Error("请至少选择一种病虫害");
        await api("subscriptions/" + (s.id || crypto.randomUUID()), "PUT", {
          ...Object.fromEntries(fd),
          pests,
          max_daily: Number(fd.get("max_daily")),
          enabled: fd.get("enabled") === "true",
        });
        close();
        toast("地区订阅已保存");
        await render();
      },
      "确认订阅",
    );
  }
  root.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.hasAttribute("data-new")) edit();
      if (b.dataset.edit)
        edit(data.subscriptions.find((s) => s.id === b.dataset.edit));
      if (b.dataset.delete)
        modal(
          "取消地区订阅",
          "<p>停止后续匹配与通知；已收到的消息仍可在检查消息中查看或删除。</p>",
          async () => {
            await api(
              "subscriptions/" + encodeURIComponent(b.dataset.delete),
              "DELETE",
            );
            close();
            await render();
          },
          "确认取消订阅",
        );
    } catch (e) {
      error(e);
    }
  };
  try {
    await render();
  } catch (e) {
    error(e);
  }
})();
