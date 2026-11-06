(async () => {
  const { esc } = FarmerUI;
  document.getElementById("app").innerHTML = AppShell.markup("history");
  const root = document.getElementById("main");
  root.classList.add("personal-main");
  const tabs =
    '<nav class="reminder-tabs"><a href="history.html">诊断记录</a><a href="plans.html" aria-current="page">执行方案</a></nav>';
  const request = async (path) => {
    const r = await fetch("/api/plans" + path, { cache: "no-store" });
    if (!r.ok) throw Error("方案不存在或暂时无法读取，请重试。");
    return r.json();
  };
  try {
    await fetch("/api/personal/session");
    const id = new URLSearchParams(location.search).get("id");
    if (!id) {
      const rows = await request("");
      root.innerHTML =
        "<h1>我的记录</h1>" +
        tabs +
        rows
          .map(
            (p) =>
              `<article class="personal-card"><h2><a href="plans.html?id=${encodeURIComponent(p.id)}">${esc(p.title)}</a></h2><p>${esc(p.created_at.slice(0, 10))} · 待执行</p><p>关联诊断：${esc(p.case_title)}</p></article>`,
          )
          .join("") +
        (rows.length
          ? ""
          : "<p>暂无执行方案。在已保存的诊断对话中说“为我生成一份执行方案”。</p>");
      return;
    }
    const p = await request("/" + encodeURIComponent(id));
    root.innerHTML =
      tabs +
      `<h1>${esc(p.title)}</h1><p>${esc(p.created_at)} · 待执行</p><a href="index.html?case=${encodeURIComponent(p.case_id)}">返回关联诊断</a><section class="personal-card"><h2>问题与依据</h2><p>作物：${esc(p.crop)} · 地区：${esc(p.region)} · 生育期：${esc(p.growth_stage)}</p><p>${esc(p.problem)}</p><h3>初步判断（未确诊）</h3><p>${esc(p.diagnosis_summary)}</p><p>${esc(p.uncertainty)}</p><h3>执行目标</h3><p>${esc(p.goal)}</p></section>${p.steps.map((s) => `<section class="personal-card"><h2>${s.number}. ${esc(s.title)}</h2><p>${esc(s.operation)}</p><p>条件：${esc(s.condition)}</p><small>待执行</small></section>`).join("")}<section class="personal-card"><h2>注意事项</h2>${p.precautions.map((x) => `<p>${esc(x)}</p>`).join("")}<h2>参考资料</h2>${SearchUI.sources({ results: p.references, message: "暂无已保存的有效网页来源；请继续核实资料。" })}</section>`;
  } catch (e) {
    root.innerHTML =
      "<h1>执行方案</h1>" + tabs + `<p role="alert">${esc(e.message)}</p>`;
  }
})();
