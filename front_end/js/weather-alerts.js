(async () => {
  const { esc, icon, toast } = FarmerUI;
  document.getElementById("app").innerHTML = AppShell.markup("reminders");
  const root = document.getElementById("main");
  root.classList.add("personal-main");
  let source,
    subscriptions = [],
    demo = null;
  const states = {
    not_checked: "尚未读取官方预警",
    stale: "上次来源数据已过期，当前状态待核对",
    ok: "来源已读取",
    partial: "部分记录通过校验",
    unsupported_source_schema: "当前来源数据尚不能确认",
    unavailable: "当前无法读取官方预警",
  };
  const time = (value) =>
    value
      ? new Date(value).toLocaleString("zh-CN", {
          timeZone: "Asia/Shanghai",
          month: "long",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "暂无记录";
  async function api(path, method = "GET", body) {
    await window.PersonalReady;
    const r = await fetch("/api/weather-alerts/" + path, {
      method,
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Zhimai-Personal": "1" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const d = await r.json();
    if (!r.ok)
      throw Error(typeof d.detail === "string" ? d.detail : "天气预警暂不可用");
    return d;
  }
  function fail(e) {
    document.getElementById("weatherError").textContent = e.message;
  }
  function advice(items) {
    return `<ol class="weather-advice">${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>`;
  }
  function demoCard(d) {
    return `<article class="personal-card weather-demo-card"><span class="weather-level orange">演示情景 · 非真实预警</span><h2>${esc(d.name)}</h2><p>${esc(d.message)}</p><h3>可以怎样防护与复查</h3>${advice(d.advice)}<p class="personal-note">${esc(d.notice)}</p><p class="personal-note">建议为一般防护方向，尚未代替本地农技审校。演示不会保存为真实预警、通知或诊断事实。</p><div class="card-actions"><button class="button secondary" id="repeatPreview">再次弹出此演示提醒</button><a class="text-button" href="index.html">带着实际情况问智麦 ${icon("arrow")}</a></div></article>`;
  }
  async function render() {
    source = await api("status");
    await window.PersonalReady;
    const r = await fetch("/api/intelligence/subscriptions", {
      cache: "no-store",
    });
    if (!r.ok) throw Error("地区订阅暂不可用");
    subscriptions = (await r.json()).subscriptions;
    root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon("clock")}留意天气变化，提前做好准备</span><h1>天气预警</h1><p>按订阅地区接收网页内提醒，结合实际苗情安排防护与复查。</p></div><a class="button secondary" href="intelligence.html">${icon("plus")}管理订阅地区</a></div><p id="weatherError" class="error" role="alert"></p><div class="reminder-tabs"><a href="personal.html?tab=tasks">提醒计划</a><a href="personal.html?tab=notifications">检查消息</a><a href="intelligence.html">地区植保订阅</a><span class="selected">天气预警</span></div>
  <section class="weather-demo-panel"><div class="weather-demo-heading"><span class="weather-level orange">现场展示</span><h2>演示一次天气预警</h2><p>无需等待真实极端天气。以下均为明确标注的演示情景，不表示当地正在发生灾害。</p></div><div class="weather-demo-controls"><label>演示地区<select id="demoRegion" aria-label="演示地区"><option value="">示例地区（不指定实际地点）</option>${subscriptions.map((s) => `<option value="${esc(s.id)}">${esc(s.province)} ${esc(s.city)}</option>`).join("")}</select></label><label>演示阶段<select id="demoAction" aria-label="演示阶段"><option>发布</option><option>升级</option><option>解除</option></select></label></div><div class="weather-scenarios">${[
    ["暴雨", "橙色", "暴雨橙色"],
    ["大风", "黄色", "大风黄色"],
    ["寒潮", "蓝色", "寒潮蓝色"],
    ["霜冻", "橙色", "霜冻橙色"],
  ]
    .map(
      ([type, level, label]) =>
        `<button class="button secondary" data-hazard="${type}" data-level="${level}">${icon("leaf")}演示${label}提醒</button>`,
    )
    .join(
      "",
    )}</div><p class="personal-note">点击后立即弹出网页提醒，并在下方展示防护建议；不需要模型、天气密钥或浏览器通知授权。</p><div id="demoResult">${demo ? demoCard(demo) : ""}</div></section>
  <h2 class="memory-section-title">真实官方预警</h2><div class="personal-banner"><p><strong>${esc(states[source.source.state] || source.source.state)}</strong><small>最近检查：${esc(time(source.source.checked_at))}。${source.warnings.length ? "以下为通过时间与地区校验的匹配记录。" : "当前没有可展示的有效匹配记录；来源不可用、未开启订阅或没有匹配记录，都不能据此断言当地没有风险。"}</small><small>官方来源：中国气象局天气网站。网页提醒需要后端运行并保持页面打开；未接入关闭网页后的推送。</small></p><a href="https://weather.cma.cn/" target="_blank" rel="noopener noreferrer">到官方天气网站核对 ${icon("arrow")}</a></div>
  <div class="personal-grid">${source.warnings.map((w) => `<article class="personal-card"><span class="weather-level ${w.level === "红色" ? "red" : w.level === "橙色" ? "orange" : ""}">${esc(w.hazard)} · ${esc(w.level)}</span><h2>${esc(w.title)}</h2><p class="personal-note">${esc(w.publisher)}<br>发布 ${esc(time(w.issued_at))} · 有效至 ${esc(time(w.expires_at))}</p><details class="explanation"><summary>官方原文与范围</summary><p>${esc(w.description)}</p><p>以发布机构原文范围为准，订阅匹配不代表照片所在地。</p></details><h3>防护与复查方向</h3>${advice(w.advice)}<p class="personal-note">${esc(w.notice)}</p></article>`).join("") || '<p class="personal-note">真实记录与演示分开显示，演示不会进入此列表。</p>'}</div><details class="personal-footnote"><summary>订阅和提醒说明</summary><p>在地区订阅中开启天气预警，选择天气类型、最低级别、频率与静默时段。仅经过来源、发布时间、有效期及行政范围校验的真实记录参与提醒。不会把天气预报文字或大模型推测当作官方预警，也不会因列表里少了一条记录就认定已解除。建议不提供农药剂量、混配或未经核对的灌溉施肥安排。</p></details>`;
  }
  root.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.hazard) {
        b.disabled = true;
        demo = await api("demo", "POST", {
          subscription_id: document.getElementById("demoRegion").value,
          hazard: b.dataset.hazard,
          level: b.dataset.level,
          action: document.getElementById("demoAction").value,
        });
        document.getElementById("demoResult").innerHTML = demoCard(demo);
        ZhimaiReminders.preview(demo);
        b.disabled = false;
      }
      if (b.id === "repeatPreview" && demo) ZhimaiReminders.preview(demo);
    } catch (error) {
      b.disabled = false;
      fail(error);
    }
  };
  try {
    await render();
  } catch (error) {
    root.innerHTML = `<p class="error" id="weatherError">${esc(error.message)}</p>`;
  }
})();
