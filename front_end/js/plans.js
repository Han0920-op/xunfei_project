(async () => {
  const { esc, icon } = FarmerUI;
  document.getElementById("app").innerHTML = AppShell.markup("history");
  const root = document.getElementById("main");
  root.classList.add("personal-main", "plans-main");
  const tabs =
    '<nav class="reminder-tabs" aria-label="记录分类"><a href="history.html">诊断记录</a><a href="plans.html" aria-current="page">执行方案</a></nav>';
  const request = async (path) => {
    const r = await fetch("/api/plans" + path, { cache: "no-store" });
    if (!r.ok) throw Error("方案不存在或暂时无法读取，请重试。");
    return r.json();
  };
  root.innerHTML =
    '<p class="personal-loading" role="status">正在读取已保存的方案…</p>';
  try {
    await fetch("/api/personal/session");
    const id = new URLSearchParams(location.search).get("id");
    if (!id) {
      const rows = await request("");
      root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon("book")}让每一步排查都有记录</span><h1>我的记录</h1><p>从一次观察，到一份可以继续跟进的方案。</p></div><a class="button secondary" href="index.html">回到对话 ${icon("arrow")}</a></div>${tabs}<div class="plan-list">${rows.map((p) => `<article class="personal-card plan-list-card"><span class="personal-badge">已保存 · 待执行</span><h2><a href="plans.html?id=${encodeURIComponent(p.id)}">${esc(p.title)}</a></h2><p class="personal-note">${esc(p.created_at.slice(0, 10))} · ${p.steps.length} 项排查步骤</p><p>关联案例：${esc(p.case_title)}</p><div class="plan-tags">${p.steps.map((s) => `<span>${esc(s.title)}</span>`).join("")}</div><a class="section-link" href="plans.html?id=${encodeURIComponent(p.id)}">查看步骤与依据 ${icon("arrow")}</a></article>`).join("") || `<section class="personal-empty">${icon("book")}<h2>把下一步，整理成方案</h2><p>在已保存的案例中点击“生成排查方案”，或直接告诉智麦你希望保存哪些排查事项。</p><a class="button primary" href="history.html">选择一个案例 ${icon("arrow")}</a></section>`}</div>`;
      return;
    }
    const p = await request("/" + encodeURIComponent(id));
    document.title = p.title + " · 智麦";
    root.innerHTML = `${tabs}<header class="plan-heading"><div><span class="receipt-state">${icon("check")}已保存 · 待执行</span><h1>${esc(p.title)}</h1><p>${esc(p.created_at.slice(0, 10))} · ${p.steps.length} 项排查步骤</p></div><a class="button secondary" href="index.html?case=${encodeURIComponent(p.case_id)}">返回关联诊断 ${icon("arrow")}</a></header><section class="plan-context"><span>${icon("leaf")} ${esc(p.crop)}</span><span>地区 · ${esc(p.region)}</span><span>生育期 · ${esc(p.growth_stage)}</span></section><section class="personal-card plan-evidence"><h2>问题与依据</h2><p>${esc(p.problem)}</p><details class="explanation"><summary>查看初步判断与不确定性</summary><p>${esc(p.diagnosis_summary)}</p><p>${esc(p.uncertainty)}</p></details></section><div class="plan-section-title"><h2>接下来这样排查</h2><p>${esc(p.goal)}</p></div><div class="plan-steps">${p.steps.map((s) => `<section class="plan-step"><span class="step-number" aria-hidden="true">${String(s.number).padStart(2, "0")}</span><div><h2>${s.number}. ${esc(s.title)}</h2><p>${esc(s.operation)}</p><div class="step-condition">${icon("clock")}<span>${esc(s.condition)}</span></div></div></section>`).join("")}</div><section class="personal-card plan-evidence"><h2>注意事项</h2>${p.precautions.map((x) => `<p>${esc(x)}</p>`).join("")}<h2>参考资料</h2>${SearchUI.sources({ results: p.references, message: p.references.length ? "已保存的参考资料，适用性仍需核对。" : "暂无已保存的有效网页来源；请继续核实资料。" })}</section>`;
  } catch (e) {
    root.innerHTML = `<h1>执行方案</h1>${tabs}<section class="personal-empty"><p role="alert">${esc(e.message)}</p><button class="button secondary" id="reloadPlans">重新读取</button></section>`;
    document.getElementById("reloadPlans").onclick = () => location.reload();
  }
})();
