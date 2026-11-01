/* Owned case follow-up workspace; all text is escaped and sources stay labelled. */
(() => {
  const { esc, icon, modal, close, toast } = FarmerUI;
  const labels = {
    collecting: "收集证据",
    needs_information: "待补充信息",
    assessing: "初步研判",
    followup: "复查跟进",
    escalated: "需农技复核",
    closed: "已结束观察",
  };
  async function api(path, method = "GET", body) {
    await window.PersonalReady;
    const r = await fetch("/api/casework/" + path, {
      method,
      headers: {
        "X-Zhimai-Personal": "1",
        ...(body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
      },
      body:
        body instanceof FormData
          ? body
          : body
            ? JSON.stringify(body)
            : undefined,
      cache: "no-store",
    });
    const data = await r.json();
    if (!r.ok)
      throw Error(
        typeof data.detail === "string" ? data.detail : "案例操作失败，请重试",
      );
    return data;
  }
  function source(s) {
    const url =
      typeof s?.url === "string" &&
      /^https:\/\/(www\.)?moa\.gov\.cn\//.test(s.url)
        ? s.url
        : "";
    return `${esc(s?.title || "已保存的查询依据")} ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">查看原文</a>` : ""}<small>发布：${esc(s?.published_on || "未标注")} · 适用地区：${esc((s?.regions || []).join("、") || "待核对")} · 农技审校待完成</small>`;
  }
  async function mount(root, c) {
    const target = document.createElement("section");
    target.className = "case-workspace";
    root.querySelector(".personal-banner").after(target);
    const path = "cases/" + encodeURIComponent(c.id),
      data = await api(path),
      state = data.state,
      a = state.assessment;
    target.innerHTML = `<div class="case-summary"><div><span class="page-eyebrow">${icon("leaf")}案例进度</span><h2>${esc(labels[state.status])}</h2><p>症状和实际措施来自你的描述；候选原因来自模型，尚未确诊。</p></div><div class="case-actions"><a class="button primary" href="index.html?case=${encodeURIComponent(c.id)}">${icon("camera")}带新照片继续咨询</a>${state.status !== "closed" ? `<a class="button secondary" href="personal.html?tab=tasks&case=${encodeURIComponent(c.id)}">${icon("clock")}约时间复查</a>` : ""}</div></div>
   <div class="case-detail-grid"><article class="personal-card"><h3>当前判断与缺失证据</h3>${a ? `<p>${esc(a.symptoms || "症状待核实")}</p><small>生育期：${esc(a.growth_stage || "未确认")} · 模型推测</small><h4>候选原因 · 未确诊</h4><ul>${a.candidate_causes.map((x) => `<li>${esc(x)}</li>`).join("") || "<li>目前证据不足</li>"}</ul><h4>还需要核对</h4><ul>${a.missing_information.map((x) => `<li>${esc(x)}</li>`).join("") || "<li>没有新增关键问题，继续观察变化</li>"}</ul>` : "<p>尚无结构化判断。继续描述异常，智麦会按需记录候选原因和缺失证据。</p>"}<p class="personal-note">已进行 ${esc(state.clarification_rounds)} 轮关键追问${state.review_required ? " · 建议农技现场复核" : ""}</p></article>
   <article class="personal-card"><h3>复查变化</h3><p>记录实际变化与措施。改善属于你的反馈，不自动认定药效。</p><button class="button secondary" data-feedback ${state.status === "closed" ? "disabled" : ""}>记录变化与措施</button><h4>更新进度</h4><label>案例状态<select id="caseStatus" aria-label="案例状态">${Object.entries(
     labels,
   )
     .filter(([v]) => data.allowed_statuses.includes(v))
     .map(
       ([v, t]) =>
         `<option value="${v}" ${v === state.status ? "selected" : ""}>${t}</option>`,
     )
     .join(
       "",
     )}</select></label><button class="button secondary" data-state>确认更新状态</button><small>结束观察会停用相关复查提醒，不代表已经治愈。</small></article></div>
   <h2 class="memory-section-title">案例照片与前后观察</h2><p class="personal-note">新照片以压缩副本私密保存，原图和定位信息不入库。上传时间不等于拍摄时间；旧案例可能只有本机照片。</p><div class="case-photos">${data.photos.map((p) => `<figure><img src="${esc(p.serverUrl)}" alt="案例诊断照片" loading="lazy"><figcaption>${esc(p.uploaded_at.slice(0, 16).replace("T", " "))} 上传 · 拍摄时间未确认</figcaption></figure>`).join("") || "<p>还没有保存到服务端的照片。</p>"}</div><div class="case-actions"><button class="button secondary" data-compare>查看前后观察</button><button class="button secondary" data-report>${icon("download")}生成依据报告</button></div><div id="caseComparison"></div><div id="caseReport"></div>
   <details class="explanation"><summary>本次案例依据与事件（${state.evidence.length} 条依据）</summary>${state.evidence.map((e) => `<div class="knowledge-quote"><strong>${esc({ official_guideline: "官方指导参考", uploaded_observation: "文档观察参考", registration_check: "登记资料核对", dated_weather: "带日期的天气查询" }[e.kind] || "查询依据")}</strong><p>${esc(e.quote || "已保存查询结果和核对状态")}</p>${source(e.source)}</div>`).join("") || "<p>尚未保存查询依据。</p>"}${data.events
     .slice(0, 20)
     .map(
       (e) =>
         `<p class="personal-note">${esc(e.created_at.slice(0, 16))} · ${esc({ followup_feedback: "用户复查反馈", status_changed: "用户更新状态", report_created: "生成报告", consultation: "咨询记录", photo_observation: "视觉初步观察", photo_uploaded: "用户补图" }[e.kind] || e.kind)}${e.notes ? " · " + esc(e.notes) : ""}${e.change ? " · " + esc({ improved: "反馈改善", unchanged: "反馈无变化", worse: "反馈恶化，需农技复核", unclear: "变化不确定" }[e.change]) : ""}</p>`,
     )
     .join("")}</details><p id="caseError" class="error" role="alert"></p>`;
    const fail = (e) =>
      (target.querySelector("#caseError").textContent = e.message);
    target.onclick = async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      try {
        if (b.hasAttribute("data-feedback"))
          modal(
            "复查：现在有什么变化？",
            `<label>与上次相比<select name="change"><option value="unclear">还不确定</option><option value="improved">有改善</option><option value="unchanged">没有明显变化</option><option value="worse">变严重了</option></select></label><label>观察变化<textarea name="notes" maxlength="2000" placeholder="异常范围、新叶、叶背等变化"></textarea></label><label>已采取的实际措施<textarea name="measures" maxlength="2000" placeholder="按实际填写；没有处理也可以记录"></textarea></label><p>补图请点“带新照片继续咨询”，会回到同一案例识别与保存。</p>`,
            async (fd) => {
              await api(path + "/feedback", "POST", Object.fromEntries(fd));
              close();
              location.reload();
            },
            "确认记录",
          );
        if (b.hasAttribute("data-state")) {
          await api(path + "/state", "PUT", {
            status: target.querySelector("#caseStatus").value,
          });
          toast("已更新案例状态");
          location.reload();
        }
        if (b.hasAttribute("data-compare")) {
          const d = await api(path + "/comparison");
          target.querySelector("#caseComparison").innerHTML =
            `<article class="personal-card"><h3>前后观察 · 非药效认定</h3>${
              d.status === "insufficient_evidence"
                ? "<p>至少需要两次成功的图片观察才能对照。</p>"
                : `<div class="case-detail-grid">${[d.before, d.after]
                    .map(
                      (x, i) =>
                        `<div><h4>${i ? "本次" : "上次"}视觉观察</h4><p>${esc(
                          (x.observations || [])
                            .filter((v) => v.status === "ok")
                            .map((v) => v.content)
                            .join("；") || "未取得可用观察",
                        )}</p></div>`,
                    )
                    .join("")}</div>`
            }<p>${esc(d.limitations)}</p></article>`;
        }
        if (b.hasAttribute("data-report")) {
          b.disabled = true;
          const d = await api(path + "/reports", "POST");
          const url =
            "/api/casework/" + path + "/reports/" + encodeURIComponent(d.id);
          target.querySelector("#caseReport").innerHTML =
            `<article class="personal-card"><span class="personal-badge">依据报告 · 已保存快照</span><h3>${esc(d.title)}</h3><p>${esc(d.notice)}</p><h4>当前不确定性</h4><ul>${d.uncertainties.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><h4>下一步</h4><ul>${d.next_steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p>${esc(d.medication_decision.notice)}</p><p>${d.references.length} 条引用，${d.rule_checks.length} 项登记核对。</p><a class="button secondary" href="${esc(url)}" download="智麦案例报告.json">下载完整报告</a><a class="button secondary" href="${esc(url)}/print" target="_blank" rel="noopener">查看可打印报告</a></article>`;
          b.disabled = false;
        }
      } catch (error) {
        b.disabled = false;
        fail(error);
      }
    };
  }
  window.CaseworkUI = { mount, api };
})();
