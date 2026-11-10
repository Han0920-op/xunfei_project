(async () => {
  const { esc, icon } = FarmerUI;
  document.getElementById("app").innerHTML = AppShell.markup("history");
  const root = document.getElementById("main");
  root.classList.add("personal-main", "plans-main");
  const tabs =
    '<nav class="reminder-tabs" aria-label="记录分类"><a href="history.html">诊断记录</a><a href="plans.html" aria-current="page">执行方案</a></nav>';
  const states = {
    pending: "待执行",
    in_progress: "进行中",
    completed: "步骤已完成",
  };
  let plan,
    saving = false,
    retry = null;
  const request = async (path, body) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const r = await fetch("/api/plans" + path, {
        cache: "no-store",
        signal: controller.signal,
        ...(body
          ? {
              method: "PATCH",
              headers: {
                "Content-Type": "application/json",
                "X-Zhimai-Personal": "1",
              },
              body: JSON.stringify(body),
            }
          : {}),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        const error = new Error(
          typeof data.detail === "string"
            ? data.detail
            : "方案暂时无法读取或保存，请重试。",
        );
        error.status = r.status;
        throw error;
      }
      return await r.json();
    } catch (error) {
      if (error.status) throw error;
      throw new Error(
        controller.signal.aborted
          ? "请求超时，进度是否保存尚未确认，请重试读取最新状态。"
          : "连接中断，进度尚未确认保存，请重试。",
      );
    } finally {
      clearTimeout(timer);
    }
  };
  const progress = (p) => {
    const done = p.steps.filter((s) => s.completed).length;
    return `<div class="plan-progress"><div><strong>已完成 ${done} / ${p.steps.length} 项</strong><span>${states[p.status] || "待执行"}</span></div><progress aria-label="方案执行进度" value="${done}" max="${p.steps.length}"></progress></div>`;
  };
  function detail(p) {
    const caseId = encodeURIComponent(p.case_id);
    document.title = p.title + " · 智麦";
    root.innerHTML = `${tabs}<header class="plan-heading"><div><span class="receipt-state">${icon("check")}已保存 · ${states[p.status] || "待执行"}</span><h1>${esc(p.title)}</h1><p>${esc(p.created_at.slice(0, 10))} · ${p.steps.length} 项排查步骤</p></div><a class="button secondary" href="index.html?case=${caseId}">返回关联诊断 ${icon("arrow")}</a></header><section class="plan-context"><span>${icon("leaf")} ${esc(p.crop)}</span><span>地区 · ${esc(p.region)}</span><span>生育期 · ${esc(p.growth_stage)}</span></section><section class="personal-card plan-evidence"><h2>问题与依据</h2><p>${esc(p.problem)}</p><details class="explanation"><summary>查看初步判断与不确定性</summary><p>${esc(p.diagnosis_summary)}</p><p>${esc(p.uncertainty)}</p></details></section><div class="plan-section-title"><h2>接下来这样排查</h2><p>${esc(p.goal)}</p></div>${progress(p)}<p class="plan-progress-note">按实际执行情况勾选，自动保存。完成排查事项不代表作物已经恢复健康。</p>${p.case_archived ? `<p class="plan-archived">关联案例已结束，方案进度暂不可修改。<a href="memory.html?case=${caseId}">查看并重新打开案例 ${icon("arrow")}</a></p>` : ""}<div class="plan-save-feedback"><p id="planSaveStatus" role="status"></p><p id="planSaveError" class="error" role="alert"></p><button class="button secondary" id="retryPlanStep" hidden>重试保存进度</button></div><div class="plan-steps">${p.steps.map((s) => `<section class="plan-step ${s.completed ? "step-completed" : ""}"><span class="step-number" aria-hidden="true">${String(s.number).padStart(2, "0")}</span><div><h2><span class="sr-only">${s.number}. </span>${esc(s.title)}</h2><p>${esc(s.operation)}</p><div class="step-condition">${icon("clock")}<span>${esc(s.condition)}</span></div><label class="step-toggle"><input type="checkbox" data-step="${s.number}" aria-label="标记完成：${esc(s.title)}" ${s.completed ? "checked" : ""} ${p.case_archived ? "disabled" : ""}><span>${s.completed ? "已完成，可取消" : "标记完成"}</span></label></div></section>`).join("")}</div><section class="plan-next-actions"><div><h2>把观察带回原案例</h2><p>记录这次的变化与实际措施，后续可以继续对照。</p></div><div><a class="button secondary" href="memory.html?case=${caseId}">${icon("history")}记录复查结果</a>${p.case_archived ? "" : `<a class="button primary" href="personal.html?tab=tasks&case=${caseId}&compose=followup">${icon("clock")}安排案例复查</a>`}</div></section><section class="personal-card plan-evidence"><h2>注意事项</h2>${p.precautions.map((x) => `<p>${esc(x)}</p>`).join("")}<h2>参考资料</h2>${SearchUI.sources({ results: p.references, message: p.references.length ? "已保存的参考资料，适用性仍需核对。" : "暂无已保存的有效网页来源；请继续核实资料。" })}</section>`;
  }
  async function update(number, completed) {
    if (saving || !plan || plan.case_archived) return;
    saving = true;
    retry = null;
    const focus = `[data-step="${number}"]`;
    root
      .querySelectorAll("[data-step]")
      .forEach((input) => (input.disabled = true));
    document.getElementById("planSaveStatus").textContent = "正在保存执行进度…";
    document.getElementById("planSaveError").textContent = "";
    document.getElementById("retryPlanStep").hidden = true;
    try {
      plan = await request(`/${encodeURIComponent(plan.id)}/steps/${number}`, {
        completed,
        revision: plan.revision || 0,
      });
      detail(plan);
      document.getElementById("planSaveStatus").textContent =
        "执行进度已保存。";
    } catch (error) {
      let message = error.message;
      if (error.status === 409) {
        try {
          plan = await request("/" + encodeURIComponent(plan.id));
          message += " 已读取最新状态，请核对后再操作。";
        } catch (_) {
          message += " 最新状态暂时无法读取，请刷新后重试。";
        }
      } else if (![401, 403, 404].includes(error.status)) {
        retry = { number, completed };
      }
      detail(plan);
      document.getElementById("planSaveError").textContent = message;
      document.getElementById("retryPlanStep").hidden = !retry;
    } finally {
      saving = false;
      root.querySelector(focus)?.focus({ preventScroll: true });
    }
  }
  root.addEventListener("change", (e) => {
    if (e.target.matches("[data-step]"))
      update(Number(e.target.dataset.step), e.target.checked);
  });
  root.addEventListener("click", (e) => {
    if (e.target.closest("#retryPlanStep") && retry)
      update(retry.number, retry.completed);
  });
  root.innerHTML =
    '<p class="personal-loading" role="status">正在读取已保存的方案…</p>';
  try {
    await fetch("/api/personal/session");
    const id = new URLSearchParams(location.search).get("id");
    if (!id) {
      const rows = await request("");
      root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon("book")}让每一步排查都有记录</span><h1>我的记录</h1><p>从一次观察，到一份可以继续跟进的方案。</p></div><a class="button secondary" href="index.html">回到对话 ${icon("arrow")}</a></div>${tabs}<div class="plan-list">${rows.map((p) => `<article class="personal-card plan-list-card"><span class="personal-badge">${p.case_archived ? "案例已结束" : states[p.status] || "待执行"}</span><h2><a href="plans.html?id=${encodeURIComponent(p.id)}">${esc(p.title)}</a></h2><p class="personal-note">${esc(p.created_at.slice(0, 10))} · ${p.steps.length} 项排查步骤</p><p>关联案例：${esc(p.case_title)}</p>${progress(p)}<div class="plan-tags">${p.steps.map((s) => `<span>${s.completed ? "✓ " : ""}${esc(s.title)}</span>`).join("")}</div><a class="section-link" href="plans.html?id=${encodeURIComponent(p.id)}">查看步骤与依据 ${icon("arrow")}</a></article>`).join("") || `<section class="personal-empty">${icon("book")}<h2>把下一步，整理成方案</h2><p>在已保存的案例中点击“生成排查方案”，或直接告诉智麦你希望保存哪些排查事项。</p><a class="button primary" href="history.html">选择一个案例 ${icon("arrow")}</a></section>`}</div>`;
      return;
    }
    plan = await request("/" + encodeURIComponent(id));
    detail(plan);
  } catch (e) {
    root.innerHTML = `<h1>执行方案</h1>${tabs}<section class="personal-empty"><p role="alert">${esc(e.message)}</p><button class="button secondary" id="reloadPlans">重新读取</button></section>`;
    document.getElementById("reloadPlans").onclick = () => location.reload();
  }
})();
