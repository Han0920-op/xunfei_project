/* Case-centered frontend workflow. Demonstration branching is not clinical advice.
 * No registration or structured-assessment endpoint is assumed to exist. */
(() => {
  "use strict";
  const Z = window.ZM,
    { icon, esc, badge, fmt } = Z;
  const paths = {
    gather_more: ["待补充信息", "amber", "补充现场信息"],
    refer_expert: ["待农技复核", "amber", "导出复核摘要"],
    observe: ["等待复查", "green", "确认复查安排"],
    label_preview: ["登记核验流程示例", "blue", "查看标签核验演示"],
    awaiting_backend: ["待结构化审核", "gray", "保留资料，等待复核"],
  };
  const scenarioName = {
    yellow: "叶片发黄",
    powder: "白色粉状物",
    aphid: "发现虫体",
    other: "其他／不确定",
    exposure: "涉及人员暴露或中毒",
  };
  const fixtures = () => [
    {
      id: "care-yellow",
      fieldId: "east",
      title: "叶片局部发黄，原因待调查",
      scenario: "yellow",
      region: "河南 · 郑州中牟",
      crop: "冬小麦",
      stage: "不清楚",
      distribution: "局部区域",
      extent: "未调查",
      symptoms:
        "流程示例：叶片局部发黄；照片、生育期和近期管理记录尚不足以区分原因。",
      capturedAt: "2026-04-18",
      createdAt: "2026-04-18T09:30:00+08:00",
      image: "assets/wheat-green.jpg",
      demo: true,
      disposition: "gather_more",
      missing: ["确认生育期", "补拍全株与田间全景", "补充近期实际管理记录"],
      observations: ["症状由示例文字提供，封面并非病斑证据"],
      candidates: ["原因尚不明确，不根据黄叶直接推荐农药"],
      actions: [],
      followups: [],
      checks: [],
      events: [],
      archived: false,
    },
    {
      id: "care-powder",
      fieldId: "river",
      title: "白色粉状物异常，等待专业复核",
      scenario: "powder",
      region: "河南 · 新乡原阳",
      crop: "冬小麦",
      stage: "拔节期",
      distribution: "多处可见",
      extent: "示例：调查方法及记录待老师审校",
      symptoms:
        "流程示例：用户描述叶片出现白色粉状物。未完成真实现场或资料核验。",
      capturedAt: "2026-04-17",
      createdAt: "2026-04-17T14:20:00+08:00",
      image: "assets/wheat-green.jpg",
      demo: true,
      disposition: "refer_expert",
      missing: ["农技复核症状与调查方法", "核对适用的防治依据"],
      observations: ["演示文字提及白色粉状物；图片仅为界面示意"],
      candidates: ["演示候选：白粉病相关症状，尚非确诊"],
      actions: [],
      followups: [],
      checks: [],
      events: [],
      archived: false,
    },
    {
      id: "care-aphid",
      fieldId: "south",
      title: "虫体观察案例，等待复查",
      scenario: "aphid",
      region: "河南 · 许昌长葛",
      crop: "冬小麦",
      stage: "待确认",
      distribution: "零星植株",
      extent: "未调查",
      symptoms: "流程示例：已记录疑似虫体，仍缺虫体近景和调查记录。",
      capturedAt: "2026-04-16",
      createdAt: "2026-04-16T10:00:00+08:00",
      image: "",
      demo: true,
      disposition: "observe",
      missing: ["补充虫体近景与调查记录"],
      observations: ["仅有用户示例描述，尚无可核对虫体图片"],
      candidates: ["虫体类别待确认"],
      actions: [],
      followups: [],
      checks: [],
      events: [],
      archived: false,
      proposedDate: "2026-04-19",
    },
  ];
  const all = () => Z.state.clinicalCases || fixtures();
  const get = (id) => all().find((c) => c.id === id);
  const mutate = (fn) =>
    Z.commit((s) => {
      s.clinicalCases ??= fixtures();
      fn(s.clinicalCases);
    });
  const update = (id, fn) =>
    mutate((cs) => {
      const c = cs.find((c) => c.id === id);
      if (c) fn(c);
    });
  const event = (c, kind, text) => {
    c.events ??= [];
    c.events.push({ id: Z.uid(), at: new Date().toISOString(), kind, text });
  };
  const stateBadge = (c) =>
    c.archived
      ? badge("已归档", "gray")
      : badge(
          (paths[c.disposition] || paths.gather_more)[0],
          (paths[c.disposition] || paths.gather_more)[1],
        );
  const sourceBadge = (c) =>
    badge(c.demo ? "流程演示 · 非真实判断" : "本地现场资料", "gray");
  const caseLink = (c) => `case.html?id=${encodeURIComponent(c.id)}`;
  const resumeLink = (c) =>
    `diagnosis.html?clinicalId=${encodeURIComponent(c.id)}`;
  const card = (c) =>
    `<article class="care-case-card"><div class="care-case-icon">${icon(c.scenario === "aphid" ? "search" : "leaf")}</div><div class="care-case-body"><div class="care-card-labels">${stateBadge(c)}${sourceBadge(c)}</div><h3><a href="${caseLink(c)}">${esc(c.title)}</a></h3><p>${esc(Z.field(c.fieldId)?.name || c.region || "未关联地块")} · ${fmt(c.capturedAt || c.createdAt)}</p><div class="care-next"><span>下一步</span>${esc(c.archived ? "查看完整处理记录" : c.missing?.[0] || "回看记录并确认复查安排")}</div></div><a class="care-card-arrow" href="${caseLink(c)}" aria-label="查看${esc(c.title)}">${icon("arrow")}</a></article>`;
  const heading = (en, title, sub, actions = "") =>
    `<div class="page-heading"><div><span class="eyebrow">${en}</span><h1>${title}</h1><p>${sub}</p></div><div class="actions">${actions}</div></div>`;
  const modeNotice = () =>
    `<div class="notice ${Z.mode === "demo" ? "amber" : ""} mb">${icon("book")}<span>${Z.mode === "demo" ? "流程演示：示例判断与登记记录均非真实诊断或有效用药依据。新增资料仅在本浏览器保存。" : "现场资料仅在本浏览器保存；原有图片、聊天接口可连接。结构化分流和真实登记核验尚待新接口，不使用演示结果补齐。"}</span></div>`;
  const phase = (current = 0) =>
    `<div class="care-phases" aria-label="案例处理流程">${["现场采集", "补充调查", "判断分流", "记录与复查"].map((x, i) => `<span class="${i === current ? "current" : ""}"><i>${i + 1}</i>${x}</span>`).join("")}</div>`;
  let historyFilter = "全部案例",
    query = "",
    detailTab = "案例概览",
    selectedCase = "",
    lastCheck = null,
    compareMode = "并排对比";
  let activeId = null,
    diagnosisState = null;
  function dashboard(root) {
    const cs = all(),
      open = cs.filter((c) => !c.archived);
    root.innerHTML =
      heading(
        "WINTER WHEAT · CROP CARE",
        "用药之前，把依据核对清楚。",
        "冬小麦病虫害辅助诊断与科学用药决策",
        `<a class="btn" href="fields.html">${icon("fields")} 地块资料</a><a class="btn primary" href="diagnosis.html">${icon("plus")} 开始辅助诊断</a>`,
      ) +
      `<section class="care-hero"><div><span class="eyebrow">从现场证据出发</span><h2>准备买药或用药？<br>先核对作物与防治对象。</h2><p>先核对登记证号与适用对象，再结合现场证据判断下一步。</p><div class="actions"><a class="btn primary" href="medication.html">${icon("book")} 核对手里的农药 ${icon("arrow")}</a><a class="btn" href="diagnosis.html">${icon("image")} 我发现了异常</a></div></div><div class="care-hero-steps"><span>${icon("search")}描述症状</span><i></i><span>${icon("chat")}补充调查</span><i></i><span>${icon("book")}核对依据</span><i></i><span>${icon("refresh")}记录复查</span><small>辅助判断 · 标签核验 · 反馈可追溯</small></div></section>${modeNotice()}<section class="stats-grid care-stats">${[
        [
          "待补充信息",
          open.filter((c) => c.disposition === "gather_more").length,
          "缺少关键调查资料",
          "chat",
        ],
        [
          "待农技复核",
          open.filter((c) =>
            ["refer_expert", "awaiting_backend"].includes(c.disposition),
          ).length,
          "复杂情况与待审核资料",
          "search",
        ],
        [
          "待复查案例",
          open.filter((c) => c.proposedDate && !c.followupDone).length,
          "安排已保存，等待现场反馈",
          "calendar",
        ],
        ["案例记录", cs.length, "演示案例与本地资料", "history"],
      ]
        .map(
          ([t, n, sub, ic]) =>
            `<div class="stat"><div><p class="stat-label">${t}</p><div class="stat-value">${n}<span>项</span></div><small>${sub}</small></div><span class="stat-icon">${icon(ic)}</span></div>`,
        )
        .join(
          "",
        )}</section><div class="section-heading"><h2>这些案例，还需要你关注</h2><a class="text-link" href="history.html">全部案例 ${icon("arrow")}</a></div><div class="care-case-grid">${open.slice(0, 3).map(card).join("") || Z.empty("暂时没有待处理案例", "发现症状时，可从照片或文字描述开始。")}</div><div class="care-bottom-grid"><section class="panel"><div class="panel-head"><h2>从一个问题开始</h2>${badge("首版拟支持场景", "gray")}</div><div class="care-scenarios">${[
        ["yellow", "叶片发黄，原因还不清楚", "补充生育期与发生分布"],
        ["powder", "叶片出现白色粉状物", "观察特征与专业依据"],
        ["aphid", "发现虫体，不知道怎么处理", "虫体近景与调查记录"],
      ]
        .map(
          ([k, t, s]) =>
            `<a href="diagnosis.html?example=${k}"><span class="entry-icon">${icon(k === "aphid" ? "search" : "leaf")}</span><span><strong>${t}</strong><small>${s} · 交互示例</small></span>${icon("arrow")}</a>`,
        )
        .join(
          "",
        )}</div></section><section class="panel care-principles"><span class="eyebrow">EVIDENCE BEFORE ACTION</span><h2>知道什么，也说明还缺什么。</h2><p>图片可见特征与疑似原因分开呈现。信息不足时先补问；登记信息匹配不代表已经需要施药。</p><button class="text-link" data-care="evidence">了解判断与来源说明 ${icon("arrow")}</button></section></div>`;
  }
  function history(root) {
    const cs = all().filter(
      (c) =>
        (historyFilter === "全部案例" ||
          (historyFilter === "已归档"
            ? c.archived
            : !c.archived && paths[c.disposition]?.[0] === historyFilter)) &&
        `${c.title}${c.region}${Z.field(c.fieldId)?.name || ""}`.includes(
          query,
        ),
    );
    root.innerHTML =
      heading(
        "CASES & FOLLOW-UP",
        "每一次判断，都有后续。",
        "回看调查、核验与实际措施，继续跟踪尚未解决的问题。",
        `<a class="btn" href="history.html?source=backend">原有诊断历史</a><a class="btn primary" href="diagnosis.html">${icon("plus")} 新建异常案例</a>`,
      ) +
      modeNotice() +
      `<div class="toolbar"><div class="segmented" aria-label="案例筛选">${["全部案例", "待补充信息", "待农技复核", "等待复查", "已归档"].map((t) => `<button data-care="filter" data-value="${t}" class="${t === historyFilter ? "active" : ""}" aria-pressed="${t === historyFilter}">${t}</button>`).join("")}</div><label class="filter-search">${icon("search")}<input id="careSearch" aria-label="搜索异常案例" placeholder="搜索症状、地块或地区" value="${esc(query)}"></label></div><p class="result-count mb">共 ${cs.length} 条案例 · 归档不代表已经治愈</p><div class="care-case-grid">${cs.map(card).join("") || Z.empty("没有符合条件的案例", "试试其他状态，或开始一次新的调查。")}</div>`;
    document.getElementById("careSearch").oninput = (e) => {
      query = e.target.value;
      const pos = e.target.selectionStart;
      history(root);
      const n = document.getElementById("careSearch");
      n.focus();
      n.setSelectionRange(pos, pos);
    };
  }
  function evidence() {
    Z.modal(
      "判断依据与来源",
      `<div class="notice amber">${icon("book")}<span>当前没有接入经过审校的病虫害防治资料或真实登记标签。演示分支仅说明交互流程，不能作为病因或防治阈值依据。</span></div><dl class="detail-list"><dt>资料名称</dt><dd>智麦 V1 前端工作流演示说明</dd><dt>资料性质</dt><dd>界面示例，非农技防治依据</dd><dt>适用范围</dt><dd>展示调查、分流、核验和复查交互</dd><dt>审校状态</dt><dd>尚未完成农技内容审校</dd></dl><h3>正式接入后，每条依据应保留</h3><p class="form-intro mt">发布单位、原文位置、发布时间、适用作物与生育期、版本、核验时间及可打开的原始地址。</p><a class="text-link" href="https://fgs.moa.gov.cn/flfg/202312/t20231205_6442161.htm" target="_blank" rel="noopener noreferrer">农药管理条例参考入口 ${icon("arrow")}</a><p class="muted mt" style="font-size:11px">此链接来自项目路线文档，本原型未核验其内容及当前适用性，也不将其作为具体病虫害结论的证据。</p>`,
      null,
      { cancel: "关闭" },
    );
  }
  function resultPanel(c) {
    if (!c)
      return `<div class="care-result-empty">${icon("search")}<h3>从已有证据，决定下一步</h3><p>确认提交现场资料后，这里显示已知信息、缺失项与当前处理路径。</p><span>疑似原因 ≠ 确诊<br>登记匹配 ≠ 需要施药</span></div>`;
    const p = paths[c.disposition] || paths.gather_more;
    return `<div class="care-result-status">${badge(p[0], p[1])}${sourceBadge(c)}<h3>${c.disposition === "awaiting_backend" ? "资料已保存，等待结构化审核" : c.disposition === "label_preview" ? "可体验登记核验流程，尚无真实用药依据" : "下一步，先把关键证据补齐"}</h3></div><div class="care-result-section"><h4>已知的现场信息</h4><ul>${(c.observations || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div><div class="care-result-section"><h4>疑似原因与判断限度</h4><ul>${(c.candidates || ["尚无经过校验的判断"]).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div><div class="care-result-section"><h4>还需要确认</h4><ul>${(c.missing?.length ? c.missing : ["仍需核对专业依据与实际处理条件"]).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div><div class="care-result-section"><button class="text-link" data-care="evidence">${icon("book")} 查看依据与来源状态</button></div><div class="care-result-actions">${c.disposition === "label_preview" ? `<a class="btn primary" href="medication.html?clinicalId=${encodeURIComponent(c.id)}">查看标签核验演示 ${icon("arrow")}</a>` : ""}${c.disposition === "refer_expert" ? `<button class="btn primary" data-care="export" data-id="${esc(c.id)}">${icon("download")} 导出农技复核摘要</button>` : ""}<a class="btn ${c.disposition === "label_preview" || c.disposition === "refer_expert" ? "" : "primary"}" href="${caseLink(c)}">查看案例与复查 ${icon("arrow")}</a></div>`;
  }
  function currentCase() {
    return get(activeId);
  }
  function attachDiagnosis(d) {
    diagnosisState = d;
    const params = new URLSearchParams(location.search);
    activeId = params.get("clinicalId");
    const c = get(activeId);
    if (c) {
      d.selectedField = c.fieldId || "";
      d.conversationId = c.chatId || null;
    }
    const intro = document.querySelector(".diagnosis-intro");
    intro.querySelector("h1").textContent = "发现异常，先把线索查清楚。";
    intro.querySelector("p").textContent =
      "冬小麦病虫害辅助诊断 · 现场调查 · 依据与处理分流";
    intro.querySelector("a").textContent = "回看案例与复查";
    const layout = document.querySelector(".diagnosis-layout");
    layout.classList.add("clinical-layout");
    const chat = layout.querySelector(".chat-card");
    const middle = document.createElement("div");
    middle.className = "clinical-middle";
    const intake = document.createElement("section");
    intake.className = "panel care-intake";
    const disclosure = document.createElement("details");
    disclosure.className = "care-chat-disclosure";
    disclosure.innerHTML = `<summary>${icon("chat")} 补充描述与对话 <span>${Z.mode === "demo" ? "固定示例回复" : "原有模型接口，尚无结构化审核"}</span>${icon("down")}</summary>`;
    disclosure.append(chat);
    middle.append(intake, disclosure);
    layout.append(middle);
    const result = document.createElement("section");
    result.className = "panel care-result";
    result.id = "clinicalResult";
    layout.append(result);
    intro.after(
      document
        .createRange()
        .createContextualFragment(
          phase(c ? (c.disposition === "gather_more" ? 1 : 2) : 0),
        ),
    );
    const example = params.get("example");
    const formCase = c || {};
    const defaultScenario = Object.keys(scenarioName).includes(example)
      ? example
      : formCase.scenario || "yellow";
    intake.innerHTML = `<div class="panel-head"><div><span class="eyebrow">FIELD INVESTIGATION</span><h2>先描述这次异常</h2><p>不清楚的项目如实保留，之后再补充。</p></div>${badge(Z.mode === "demo" ? "演示分流" : "本地采集", "gray")}</div><form id="careIntake"><div class="care-form-body"><div class="form-grid"><label>所属地块<select name="fieldId" id="intakeField"><option value="">临时案例／暂不关联地块</option>${Z.fieldOptions(formCase.fieldId || params.get("fieldId"))}</select></label><label>所在地区 <span>*</span><input name="region" required maxlength="100" placeholder="例如：河南郑州中牟" value="${esc(formCase.region || "")}"></label><label>作物<select name="crop"><option ${formCase.crop === "冬小麦" ? "selected" : ""}>冬小麦</option><option ${formCase.crop === "其他作物" ? "selected" : ""}>其他作物</option></select></label><label>当前生育期<select name="stage">${["不清楚", "播种出苗期", "分蘖期", "越冬期", "返青期", "拔节期", "孕穗期", "抽穗扬花期", "灌浆期", "成熟期"].map((t) => `<option ${t === formCase.stage ? "selected" : ""}>${t}</option>`).join("")}</select></label><label>主要异常<select name="scenario" id="intakeScenario">${Object.entries(
      scenarioName,
    )
      .map(
        ([k, t]) =>
          `<option value="${k}" ${k === defaultScenario ? "selected" : ""}>${t}</option>`,
      )
      .join(
        "",
      )}</select></label><label>照片拍摄／观察日期<input type="date" name="capturedAt" max="${Z.today()}" value="${esc(formCase.capturedAt || "")}"><small>无法确认时可留空，不用上传时间代替。</small></label><label class="full">异常分布<select name="distribution"><option>尚未调查</option>${["零星植株", "局部区域", "多处可见", "全田普遍"].map((t) => `<option ${formCase.distribution === t ? "selected" : ""}>${t}</option>`).join("")}</select></label><label class="full">现场症状描述 <span>*</span><textarea name="symptoms" rows="3" required maxlength="2500" placeholder="异常出现在哪个部位？什么时候发现？">${esc(formCase.symptoms || "")}</textarea></label></div><div class="care-question-box"><h3>再补充一条关键调查</h3><p id="questionWhy"></p><label>调查结果与方法（可填“未调查”）<textarea name="extent" rows="2" maxlength="1000" placeholder="如实描述发生程度、调查方法与单位；不要猜测。">${esc(formCase.extent || "")}</textarea></label><label class="mt">近期是否采取过措施？<select name="recentAction"><option>不清楚／尚未补充</option><option ${formCase.recentAction === "明确尚未处理" ? "selected" : ""}>明确尚未处理</option><option ${formCase.recentAction === "已经采取措施，详见描述" ? "selected" : ""}>已经采取措施，详见描述</option></select></label><label class="mt">补充说明<textarea name="management" rows="2" maxlength="1500" placeholder="已知的近期水肥、用药或环境变化。">${esc(formCase.management || "")}</textarea></label></div><div class="notice" id="intakeImageNote">${icon("image")}<span>照片可在左侧选择。只选图不会启动调查；无图时可以先描述症状。</span></div><p id="intakeError" class="form-error" role="alert"></p></div><div class="care-form-footer"><small>保存后仍可继续补充，不生成自动处方。</small><button class="btn primary" type="submit">${icon("check")} ${c ? "保存补充并更新流程" : "确认提交现场资料"}</button></div></form>`;
    const form = document.getElementById("careIntake");
    const updateQuestion = () => {
      const s = form.elements.scenario.value;
      document.getElementById("questionWhy").textContent =
        s === "aphid"
          ? "虫体出现在哪些部位？如已调查，请记录方法、虫量与单位；尚未辨认时先补近景。"
          : s === "powder"
            ? "白色粉状物出现在哪些部位、范围如何？发生程度需结合可审核的调查方法。"
            : s === "exposure"
              ? "涉及人员暴露时，停止农业诊断流程，优先联系当地急救或专业中毒咨询服务。"
              : "异常是零星还是普遍出现？分布、生育期和近期操作有助于安排进一步调查。";
    };
    updateQuestion();
    form.elements.scenario.onchange = updateQuestion;
    document.getElementById("intakeField").onchange = () => {
      const f = Z.field(form.elements.fieldId.value);
      if (f) {
        form.elements.region.value = f.location;
        if ([...form.elements.stage.options].some((o) => o.value === f.stage))
          form.elements.stage.value = f.stage;
      }
    };
    if (!c && params.get("fieldId"))
      document.getElementById("intakeField").onchange();
    form.onsubmit = async (e) => {
      e.preventDefault();
      const submit = form.querySelector("[type=submit]");
      submit.disabled = true;
      try {
        if (d.imageStatus === "recognizing")
          throw new Error("请等待当前图片观察完成，或移除图片后提交。");
        if (d.imageStatus === "failed")
          throw new Error("当前图片观察失败，请重试或移除图片，不使用旧结果。");
        const fd = new FormData(form);
        if (!fd.get("symptoms").trim() || !fd.get("region").trim())
          throw new Error("请填写地区与现场症状。");
        let image = currentCase()?.image || "";
        if (d.file) image = await fileData(d.file, 4);
        const record = {
          ...JSON.parse(JSON.stringify(currentCase() || {})),
          id: activeId || Z.uid(),
          fieldId: fd.get("fieldId"),
          region: fd.get("region").trim(),
          crop: fd.get("crop"),
          stage: fd.get("stage"),
          scenario: fd.get("scenario"),
          distribution: fd.get("distribution"),
          symptoms: fd.get("symptoms").trim(),
          extent: fd.get("extent").trim() || "未调查",
          recentAction: fd.get("recentAction"),
          management: fd.get("management").trim(),
          capturedAt: fd.get("capturedAt"),
          image,
          photoIsIllustration: d.file
            ? false
            : (currentCase()?.photoIsIllustration ??
              Boolean(currentCase()?.demo)),
          createdAt: currentCase()?.createdAt || new Date().toISOString(),
          demo: Z.mode === "demo",
          archived: false,
        };
        record.title = `${scenarioName[record.scenario]} · 现场调查`;
        record.actions ??= [];
        record.followups ??= [];
        record.checks ??= [];
        record.events ??= [];
        if (!record.assessments?.length && currentCase()) {
          const previous = currentCase();
          record.assessments = [
            {
              at: previous.createdAt,
              disposition: previous.disposition,
              candidates: previous.candidates || [],
              missing: previous.missing || [],
              demo: previous.demo,
            },
          ];
        }
        assess(record);
        record.assessments ??= [];
        record.assessments.push({
          at: new Date().toISOString(),
          disposition: record.disposition,
          candidates: [...record.candidates],
          missing: [...record.missing],
          demo: record.demo,
        });
        event(record, "调查资料", record.symptoms);
        event(
          record,
          "流程分流",
          `${paths[record.disposition]?.[0]}：${record.missing.join("；")}（${record.demo ? "交互演示" : "等待后端审核"}）`,
        );
        if (
          mutate((cs) => {
            const i = cs.findIndex((x) => x.id === record.id);
            if (i < 0) cs.unshift(record);
            else cs[i] = record;
          })
        ) {
          activeId = record.id;
          d.selectedField = record.fieldId;
          window.history.replaceState(
            null,
            "",
            `diagnosis.html?clinicalId=${encodeURIComponent(activeId)}`,
          );
          document.getElementById("clinicalResult").innerHTML =
            resultPanel(record);
          document.querySelector(".care-phases").outerHTML = phase(
            record.disposition === "gather_more" ? 1 : 2,
          );
          submit.innerHTML = icon("check") + " 保存补充并更新流程";
          document.getElementById("intakeError").textContent = "";
          Z.toast(
            Z.mode === "demo"
              ? "资料已保存，已展示演示分流"
              : "资料已保存，等待后端结构化审核",
          );
        }
      } catch (err) {
        document.getElementById("intakeError").textContent = err.message;
      } finally {
        submit.disabled = false;
      }
    };
    result.innerHTML = resultPanel(c);
    Z.Care.photoChanged();
  }
  function assess(c) {
    c.observations = [
      `用户描述：${c.symptoms}`,
      `分布：${c.distribution}；程度：${c.extent}`,
    ];
    c.missing = [];
    if (!c.capturedAt) c.missing.push("确认拍摄／观察时间");
    if (c.stage === "不清楚") c.missing.push("确认当前生育期");
    if (c.distribution === "尚未调查") c.missing.push("补充异常分布");
    if (!c.extent || c.extent === "未调查")
      c.missing.push("补充调查方法、发生程度及单位");
    if (c.recentAction === "不清楚／尚未补充")
      c.missing.push("确认近期是否采取过措施");
    if (c.scenario === "exposure") {
      c.disposition = "refer_expert";
      c.candidates = ["此情境停止农业诊断，不提供用药建议"];
      c.missing = [
        "优先联系当地急救／专业中毒咨询服务，提供产品标签与暴露情况",
      ];
      return;
    }
    if (c.crop !== "冬小麦") {
      c.disposition = "refer_expert";
      c.candidates = ["当前首版仅覆盖冬小麦，其他作物不套用同一规则"];
      c.missing = ["请向相关作物的农技人员咨询"];
      return;
    }
    if (Z.mode !== "demo") {
      c.disposition = "awaiting_backend";
      c.candidates = ["现有接口尚未提供经过结构化校验的候选原因与证据编号"];
      c.missing.push("由后端完成观察依据、适用规则与分流校验");
      return;
    }
    if (c.scenario === "yellow" || c.scenario === "other") {
      c.disposition = "gather_more";
      c.candidates = ["当前原因仍不明确，黄叶或外观变化不能直接支持用药"];
      c.missing.push("补充全景、局部特征与近期管理背景，并核对专业资料");
    } else {
      c.candidates = [
        c.scenario === "powder"
          ? "演示候选：白粉病相关症状，未经真实诊断"
          : "演示候选：蚜虫相关观察，虫体与调查记录仍需专业核对",
      ];
      c.disposition = c.missing.length ? "gather_more" : "label_preview";
      c.missing.push("核对农技依据及是否达到防治条件；演示不提供真实阈值");
    }
  }
  async function fileData(file, max = 2) {
    if (!file?.size) return "";
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type))
      throw new Error("请选择 JPG、PNG 或 WEBP 图片。");
    if (file.size > max * 1024 * 1024)
      throw new Error(`图片请控制在 ${max} MB 以内。`);
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error("图片读取失败。"));
      r.readAsDataURL(file);
    });
  }
  function casePage(root, params) {
    const c = get(params.get("id"));
    if (!c) {
      root.innerHTML = Z.empty(
        "没有找到此案例",
        "请从案例列表重新选择。",
        '<a class="btn primary" href="history.html">返回案例列表</a>',
      );
      return;
    }
    root.innerHTML =
      `<a class="back-link" href="history.html">${icon("arrow")} 返回案例与复查</a>` +
      heading(
        "CASE FILE · EVIDENCE & FOLLOW-UP",
        esc(c.title),
        `${esc(Z.field(c.fieldId)?.name || c.region)} · 创建于 ${fmt(c.createdAt)}`,
        `<button class="btn" data-care="export" data-id="${esc(c.id)}">${icon("download")} 导出复核摘要</button><a class="btn primary" href="${resumeLink(c)}">${icon("edit")} 继续补充调查</a>`,
      ) +
      `<div class="care-case-strip"><div>${stateBadge(c)}${sourceBadge(c)}</div><span>作物：${esc(c.crop)}　生育期：${esc(c.stage)}　观察日期：${fmt(c.capturedAt)}</span></div><div class="field-detail-tabs" aria-label="案例栏目">${["案例概览", "调查与依据", "实际措施", "复查记录"].map((t) => `<button data-care="tab" data-value="${t}" class="${detailTab === t ? "active" : ""}" aria-pressed="${detailTab === t}">${t}</button>`).join("")}</div><div class="care-detail-grid"><div>${
        detailTab === "案例概览"
          ? `<section class="panel care-detail-panel"><h2>本次现场资料</h2>${c.image ? `<figure class="care-detail-photo"><img src="${Z.safeImage(c.image)}" alt="本次现场图片${c.demo ? "，演示示意" : ""}"><figcaption>${c.demo && c.photoIsIllustration !== false ? "演示图片，不作为症状识别证据" : "用户提交的现场照片；不等同于已形成诊断"} · ${fmt(c.capturedAt)}</figcaption></figure>` : ""}<p class="care-paragraph">${esc(c.symptoms)}</p><dl class="detail-list"><dt>异常分布</dt><dd>${esc(c.distribution)}</dd><dt>调查情况</dt><dd>${esc(c.extent)}</dd><dt>近期措施</dt><dd>${esc(c.recentAction || "尚未补充")}</dd><dt>补充说明</dt><dd>${esc(c.management || "暂无")}</dd></dl></section><section class="panel care-detail-panel mt"><h2>处理过程</h2>${timeline(c)}</section>`
          : detailTab === "调查与依据"
            ? `<section class="panel care-detail-panel"><h2>当前调查与判断</h2>${resultPanel(c)}<h3 class="mt">判断修订记录</h3>${
                (c.assessments || [])
                  .slice()
                  .reverse()
                  .map(
                    (a) =>
                      `<article class="care-log"><div>${badge(paths[a.disposition]?.[0] || "待审核", "gray")}<small>${fmt(a.at)} · ${a.demo ? "流程演示" : "待后端审核"}</small></div><p>${esc((a.missing || []).join("；"))}</p></article>`,
                  )
                  .join("") || '<p class="muted mt">尚未产生新的判断版本。</p>'
              }<h3 class="mt">登记核验记录</h3>${checksHTML(c)}</section>`
            : detailTab === "实际措施"
              ? `<section class="panel care-detail-panel"><div class="actions" style="justify-content:space-between"><h2>如实记录采取的措施</h2><button class="btn primary" data-care="action" data-id="${esc(c.id)}">${icon("plus")} 记录实际措施</button></div><p class="muted mt">系统判断与实际操作分开保存，不会默认视为已经执行。</p>${actionsHTML(c)}</section>`
              : `<section class="panel care-detail-panel"><div class="actions" style="justify-content:space-between"><h2>复查与现场反馈</h2><button class="btn primary" data-care="followup" data-id="${esc(c.id)}">${icon("plus")} 提交复查</button></div><p class="muted mt">用户观察与自动判断分开；任务完成不等于防治有效。</p>${followupsHTML(c)}<a class="btn mt" href="compare.html?clinicalId=${encodeURIComponent(c.id)}">${icon("compare")} 打开前后对比</a></section>`
      }</div><aside><section class="panel care-detail-panel"><h2>下一步</h2><p class="care-paragraph">${esc(c.missing?.[0] || "继续跟踪现场变化")}</p><div class="care-side-buttons"><button class="btn soft" data-care="schedule" data-id="${esc(c.id)}">${icon("calendar")} 确认复查安排</button><a class="btn" href="medication.html?clinicalId=${encodeURIComponent(c.id)}">${icon("book")} 查看登记核验</a><button class="text-link" data-care="evidence">查看资料与来源状态 ${icon("arrow")}</button></div>${c.proposedDate ? `<p class="notice mt">已保存复查日期：${fmt(c.proposedDate)}。尚未接入后台推送。</p>` : ""}</section><section class="panel care-detail-panel mt"><h3>跟踪状态</h3><p class="care-paragraph">归档只表示结束本轮跟踪，不代表已治愈或确认用药有效。</p><button class="btn small" data-care="archive" data-id="${esc(c.id)}">${c.archived ? "重新打开跟踪" : "结束跟踪并归档"}</button></section></aside></div>`;
  }
  function timeline(c) {
    const rows = [
      { kind: "建立案例", at: c.createdAt, text: c.symptoms },
      ...(c.events || []),
    ];
    return `<div class="care-audit">${rows
      .slice()
      .reverse()
      .map(
        (e) =>
          `<article><i></i><small>${fmt(e.at)} · ${esc(e.kind)}</small><p>${esc(e.text)}</p></article>`,
      )
      .join("")}</div>`;
  }
  function actionsHTML(c) {
    return (
      (c.actions || [])
        .slice()
        .reverse()
        .map(
          (a) =>
            `<article class="care-log"><div>${badge(a.kind, "blue")}<small>${fmt(a.date)} · 用户确认的实际记录</small></div><p>${esc(a.note)}</p>${a.product ? `<p>产品／登记号：${esc(a.product)}</p><p class="notice amber">尚无已核验标签，不能判定本次操作与标签的一致性。</p>` : ""}</article>`,
        )
        .join("") ||
      Z.empty(
        "暂未记录实际措施",
        "尚未处理也可以如实记录，不需要为了完成流程填写用药。",
      )
    );
  }
  function followupsHTML(c) {
    return (
      (c.followups || [])
        .slice()
        .reverse()
        .map(
          (f) =>
            `<article class="care-log"><div>${badge("用户反馈：" + f.outcome, f.outcome === "加重" ? "amber" : "gray")}<small>${fmt(f.date)}</small></div>${f.image ? `<img class="care-followup-photo" src="${Z.safeImage(f.image)}" alt="复查照片">` : ""}<p>${esc(f.note)}</p><small>系统整理：${f.outcome === "加重" ? "用户报告加重，建议农技复核；不自动归因于药效或病因。" : "仍需结合拍摄条件、现场调查与期间措施判断。"}</small></article>`,
        )
        .join("") ||
      Z.empty(
        "等待下一次现场反馈",
        "补充照片、调查情况与观察结果，让本次案例有后续。",
      )
    );
  }
  function checksHTML(c) {
    return (
      (c.checks || [])
        .slice()
        .reverse()
        .map(
          (x) =>
            `<article class="care-log"><div>${badge(x.summary, x.kind === "mismatch" ? "red" : "gray")}<small>${fmt(x.at)}</small></div><p>登记号：${esc(x.number)} · ${esc(x.crop)} / ${esc(x.target)}</p><small>${x.demo ? "虚构样例，非真实登记核验" : "接口未接入，未形成核验结论"}</small></article>`,
        )
        .join("") ||
      '<p class="muted mt">尚无登记核验记录。登记查询不等于用药建议。</p>'
    );
  }
  function exportCase(id) {
    const c = get(id);
    if (!c) return;
    const text = [
      `# 智麦异常案例：${c.title}`,
      `来源：${c.demo ? "流程演示，非真实诊断" : "用户提交资料，待结构化审核"}`,
      `地区：${c.region}\n作物：${c.crop}\n生育期：${c.stage}\n观察日期：${c.capturedAt || "未确认"}`,
      `## 症状与调查\n${c.symptoms}\n分布：${c.distribution}\n程度及方法：${c.extent}`,
      `## 当前处理路径\n${paths[c.disposition]?.[0] || "待审核"}`,
      `## 缺失信息\n${(c.missing || []).map((x) => "- " + x).join("\n")}`,
      `## 实际措施\n${(c.actions || []).map((a) => `${a.date} ${a.kind}：${a.note} ${a.product || ""}`).join("\n") || "未记录"}`,
      `## 复查\n${(c.followups || []).map((f) => `${f.date} 用户反馈：${f.outcome}；${f.note}`).join("\n") || "未记录"}`,
      `## 核验记录\n${(c.checks || []).map((x) => `${x.at} ${x.number}：${x.summary}（${x.demo ? "演示" : "未接入核验接口"}）`).join("\n") || "无"}`,
      "注：本文件为文字摘要，原始照片请另行保存。没有已核验标签时不生成用药数值。",
    ];
    Z.download(`智麦-${c.title}-复核摘要.md`, text.join("\n\n"));
    Z.toast("复核文字摘要已导出，原始照片请另行保存");
  }
  function actionDialog(id) {
    Z.modal(
      "记录实际采取的措施",
      `<p class="form-intro">如实保存发生过的操作；系统不自动视为建议已执行。</p><div class="form-grid"><label>所属日期<input type="date" name="date" required value="${Z.today()}" max="${Z.today()}"></label><label>措施类型<select name="kind" id="actualKind"><option>暂未处理</option><option>农业管理措施</option><option>实际用药</option><option>已咨询农技人员</option><option>其他措施</option></select></label><label class="full" id="productField" hidden>实际产品名称／登记号<input name="product" maxlength="160" placeholder="按实际标签记录，不从演示结果填入"></label><label class="full">实际情况说明<textarea name="note" required rows="4" maxlength="3000" placeholder="哪天做了什么，或为什么暂未处理？"></textarea></label><label class="full care-confirm"><input type="checkbox" name="confirmed" required> 我确认这是真实发生的操作或决定，不是自动生成的建议。</label></div>`,
      (fd) => {
        const note = fd.get("note").trim();
        if (!note) throw new Error("请填写实际情况。");
        if (fd.get("kind") === "实际用药" && !fd.get("product").trim())
          throw new Error("请记录实际产品信息；不清楚时可注明待核对。");
        if (
          update(id, (c) => {
            c.actions ??= [];
            c.actions.push({
              id: Z.uid(),
              date: fd.get("date"),
              kind: fd.get("kind"),
              note,
              product:
                fd.get("kind") === "实际用药" ? fd.get("product").trim() : "",
              userConfirmed: true,
            });
            event(c, "实际措施", `${fd.get("kind")}：${note}`);
          })
        ) {
          Z.closeModal();
          detailTab = "实际措施";
          refresh();
          Z.toast("实际措施已保存");
        }
      },
    );
    document.getElementById("actualKind").onchange = (e) =>
      (document.getElementById("productField").hidden =
        e.target.value !== "实际用药");
  }
  function schedule(id) {
    const c = get(id);
    Z.modal(
      "确认下一次复查安排",
      `<p class="form-intro">由你确认观察时间和需要补充的信息；当前仅保存安排，不发送后台通知。</p><label>复查日期<input type="date" name="date" required value="${esc(c?.proposedDate || Z.today())}"></label><label class="mt">复查重点<textarea name="note" required rows="3" maxlength="1000">${esc(c?.missing?.[0] || "补充现场照片与调查记录")}</textarea></label>`,
      (fd) => {
        if (!fd.get("note").trim()) throw new Error("请填写复查重点。");
        if (
          update(id, (c) => {
            c.proposedDate = fd.get("date");
            c.followupDone = false;
            c.followupNote = fd.get("note").trim();
            event(c, "用户确认复查", `${c.proposedDate}：${c.followupNote}`);
          })
        ) {
          Z.closeModal();
          refresh();
          Z.toast("复查安排已保存，未开启后台推送");
        }
      },
    );
  }
  function followup(id) {
    Z.modal(
      "提交本次现场复查",
      `<div class="form-grid"><label>复查日期<input type="date" name="date" required max="${Z.today()}" value="${Z.today()}"></label><label>你观察到的变化<select name="outcome"><option>无法判断</option><option>改善</option><option>无明显变化</option><option>加重</option></select></label><label class="full">现场情况<textarea name="note" required rows="4" maxlength="3000" placeholder="症状范围、调查情况、期间措施与仍待确认的内容。"></textarea></label><label class="full file-label">复查照片（可选，最大 2 MB）<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><label class="full care-confirm"><input type="checkbox" name="comparable"> 已确认与上次照片的采样位置、角度和光照相近。</label></div>`,
      async (fd) => {
        if (!fd.get("note").trim()) throw new Error("请填写本次现场情况。");
        const image = await fileData(fd.get("photo"));
        if (
          update(id, (c) => {
            c.followupDone = true;
            c.followups ??= [];
            c.followups.push({
              id: Z.uid(),
              date: fd.get("date"),
              outcome: fd.get("outcome"),
              note: fd.get("note").trim(),
              image,
              comparable: fd.has("comparable"),
            });
            if (fd.get("outcome") === "加重") {
              c.disposition = "refer_expert";
              c.missing = ["用户报告症状加重，需农技人员复核"];
            }
            c.archived = false;
            event(
              c,
              "提交复查",
              `用户反馈${fd.get("outcome")}：${fd.get("note").trim()}`,
            );
          })
        ) {
          Z.closeModal();
          detailTab = "复查记录";
          refresh();
          Z.toast("复查已保存，用户反馈不等同于已确认药效");
        }
      },
    );
  }
  const snapshots = {
    "DEMO-WHEAT-001": {
      crop: "冬小麦",
      target: "白粉病",
      name: "流程演示产品 A",
      form: "剂型／含量占位，非实际产品",
      complete: true,
    },
    "DEMO-APHID-001": {
      crop: "冬小麦",
      target: "蚜虫",
      name: "流程演示产品 B",
      form: "剂型／含量占位，非实际产品",
      complete: true,
    },
    "DEMO-MISMATCH-001": {
      crop: "水稻",
      target: "稻飞虱",
      name: "不匹配流程样例",
      form: "不提供实际产品信息",
      complete: true,
    },
    "DEMO-INCOMPLETE-001": {
      crop: "冬小麦",
      target: "白粉病",
      name: "信息缺失流程样例",
      form: "未提供",
      complete: false,
    },
  };
  function medication(root, params) {
    selectedCase = params.get("clinicalId") || selectedCase;
    const c = get(selectedCase);
    root.innerHTML =
      heading(
        "EVIDENCE-BASED PESTICIDE CHECK",
        "先核对条件，再看登记标签。",
        "逐项解释已知信息与不匹配原因，不自动开具用药处方。",
        `<a class="btn" href="history.html">${icon("history")} 回看案例</a>`,
      ) +
      modeNotice() +
      `<div class="care-medication-grid"><div><section class="panel care-detail-panel"><span class="eyebrow">01 · CASE CONTEXT</span><h2>当前需要核对的情况</h2><label class="mt">关联异常案例<select id="medCase"><option value="">独立核对登记事实，不关联案例</option>${all()
        .map(
          (x) =>
            `<option value="${esc(x.id)}" ${x.id === selectedCase ? "selected" : ""}>${esc(x.title)}</option>`,
        )
        .join(
          "",
        )}</select></label>${c ? `<div class="care-context-note">${stateBadge(c)}<p>${esc(c.symptoms)}</p><small>${esc(c.disposition === "label_preview" ? "当前仅可体验标签核验，不代表真实防治条件已满足。" : "当前案例尚需调查或复核。可以独立查阅登记事实，不自动成为本案例用药方案。")}</small><a class="text-link" href="${resumeLink(c)}">返回补充调查 ${icon("arrow")}</a></div>` : '<p class="form-intro mt">已有产品时可以先核对登记事实。查询到某条记录不表示它适合本次田间问题。</p>'}</section><section class="panel care-detail-panel mt"><span class="eyebrow">02 · REGISTRATION & LABEL</span><h2>输入登记信息</h2><form id="registrationForm"><label class="mt">登记证号<input name="number" required maxlength="100" placeholder="输入标签上的登记证号" autocomplete="off"></label><div class="form-grid mt"><label>核对作物<input name="crop" required maxlength="60" value="${esc(c?.crop || "冬小麦")}"></label><label>核对防治对象<input name="target" required maxlength="80" placeholder="例如：已确认的防治对象" value="${c?.scenario === "powder" ? "白粉病" : c?.scenario === "aphid" ? "蚜虫" : ""}"></label></div><p class="form-intro mt">字段来自当前输入，不代表病因已确认。剂型、含量和来源状态还需对应实际标签。</p><p id="registrationError" class="form-error" role="alert"></p><button class="btn primary" type="submit">${icon("search")} ${Z.mode === "demo" ? "核对演示登记记录" : "检查核验服务状态"}</button></form><details class="care-package"><summary>${icon("image")} 拍了包装标签？先预览并确认登记号</summary><label class="file-label mt">选择清晰标签照片<input id="packagePhoto" type="file" accept="image/jpeg,image/png,image/webp"></label><img id="packagePreview" alt="用户选择的包装标签" hidden><p id="packageStatus" class="muted mt">尚未接入标签 OCR；照片不会被当作已核验登记信息。请手动输入并确认登记证号。</p></details>${
        Z.mode === "demo"
          ? `<details class="care-demo-samples"><summary>没有登记号？体验四种演示结果</summary><p>以下均为虚构编号，不对应真实产品或有效标签。</p>${Object.entries(
              snapshots,
            )
              .map(
                ([n, s]) =>
                  `<button class="btn small" data-care="sample-registration" data-number="${n}">${s.name}</button>`,
              )
              .join("")}</details>`
          : ""
      }</section></div><section class="panel care-detail-panel care-verification" id="registrationResult">${lastCheck ? verificationHTML(lastCheck) : `<div class="care-result-empty">${icon("book")}<h3>核对每一个适用条件</h3><p>提交后按作物、对象、产品规格及来源状态逐项展示。不匹配或缺少有效依据时，不展示具体用药数值。</p></div>`}</section></div>`;
    document.getElementById("medCase").onchange = (e) => {
      selectedCase = e.target.value;
      lastCheck = null;
      window.history.replaceState(
        null,
        "",
        `medication.html${selectedCase ? "?clinicalId=" + encodeURIComponent(selectedCase) : ""}`,
      );
      medication(root, new URLSearchParams(location.search));
    };
    let packageVersion = 0;
    document.getElementById("packagePhoto").onchange = async (e) => {
      const version = ++packageVersion;
      const file = e.target.files[0];
      if (!file) return;
      try {
        const src = await fileData(file, 4);
        if (version !== packageVersion) return;
        document.getElementById("packagePreview").src = src;
        document.getElementById("packagePreview").hidden = false;
        document.getElementById("packageStatus").textContent =
          "标签照片仅在本页预览，未执行 OCR 或官方核验。请人工确认登记号后提交。";
      } catch (err) {
        if (version !== packageVersion) return;
        document.getElementById("packageStatus").textContent = err.message;
        document.getElementById("packagePreview").hidden = true;
      }
    };
    document.getElementById("registrationForm").onsubmit = (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const number = fd.get("number").trim().toUpperCase(),
        crop = fd.get("crop").trim(),
        target = fd.get("target").trim();
      if (!number || !crop || !target) {
        document.getElementById("registrationError").textContent =
          "请填写登记证号、作物和防治对象。";
        return;
      }
      const s = Z.mode === "demo" ? snapshots[number] : null;
      const kind =
        Z.mode !== "demo"
          ? "unavailable"
          : !s
            ? "not_found"
            : !s.complete
              ? "incomplete"
              : s.crop !== crop || s.target !== target
                ? "mismatch"
                : "example_match";
      const summary = {
        unavailable: "核验服务尚未接入",
        not_found: "未找到该演示编号",
        incomplete: "示例信息不完整",
        mismatch: "示例字段明确不匹配",
        example_match: "演示字段一致，真实状态未核验",
      }[kind];
      const check = {
        id: Z.uid(),
        number,
        crop,
        target,
        kind,
        summary,
        snapshot: s || null,
        at: new Date().toISOString(),
        demo: Z.mode === "demo",
        clinicalId: selectedCase || null,
      };
      if (
        selectedCase &&
        !update(selectedCase, (c) => {
          c.checks ??= [];
          c.checks.push(check);
          event(c, "登记核对", `${number}：${summary}`);
        })
      )
        return;
      lastCheck = check;
      document.getElementById("registrationResult").innerHTML =
        verificationHTML(check);
      document.getElementById("registrationError").textContent = "";
    };
  }
  function verificationHTML(x) {
    const s = x.snapshot;
    const tone = x.kind === "mismatch" ? "red" : "amber";
    return `<span class="eyebrow">03 · VERIFICATION RESULT</span><p class="care-paragraph">本次登记号：${esc(x.number)}</p>${badge(x.summary, tone)}<h2 class="mt">${x.kind === "example_match" ? "字段一致，也要核对实际依据。" : x.kind === "unavailable" ? "等待真实核验接口接入。" : x.kind === "not_found" ? "请检查编号，或切换流程样例。" : "先把缺项和差异看清楚。"}</h2><p class="care-paragraph">${x.kind === "not_found" ? "当前只查询了本地演示样例，不能据此断言真实登记号不存在。" : x.kind === "unavailable" ? "本次没有调用官方登记查询服务，也没有以演示记录补齐结果。" : "此记录是虚构的前端流程样例，未对应任何真实有效农药登记，不能用于实际施药。"}</p><div class="care-check-table-wrap"><table class="care-check-table"><thead><tr><th>核对项</th><th>本次输入</th><th>样例记录</th><th>状态</th></tr></thead><tbody>${[
      ["作物", x.crop, s?.crop],
      ["防治对象", x.target, s?.target],
      ["剂型／含量", "尚未提供实际标签", s?.form],
      ["登记有效状态", "使用时点待确认", null],
    ]
      .map(
        ([name, input, value], i) =>
          `<tr><td>${name}</td><td>${esc(input)}</td><td>${esc(value || "未提供")}</td><td>${i < 2 && value ? badge(input === value ? "样例一致" : "不匹配", input === value ? "gray" : "red") : badge("待核实", "amber")}</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table></div><dl class="detail-list"><dt>数据性质</dt><dd>${x.demo ? "虚构流程样例，非真实登记快照" : "核验服务未接入"}</dd><dt>本次操作时间</dt><dd>${fmt(x.at)}（不是官方核验日期）</dd><dt>登记来源</dt><dd>尚无可核对的真实来源、标签版本和核验日期</dd><dt>当前结论</dt><dd>没有已核验标签，不提供具体用量、混配比例或安全间隔期</dd></dl><div class="actions"><button class="btn" data-care="label-preview">${icon("book")} 查看字段与来源说明</button>${x.clinicalId ? `<button class="btn soft" data-care="action" data-id="${esc(x.clinicalId)}">${icon("edit")} 记录实际措施</button><a class="text-link" href="case.html?id=${encodeURIComponent(x.clinicalId)}">回到本次案例 ${icon("arrow")}</a>` : ""}</div>`;
  }
  function comparison(root, params) {
    const id = params.get("clinicalId") || all()[0]?.id,
      c = get(id);
    if (!c) {
      root.innerHTML = Z.empty(
        "请先选择一个异常案例",
        "从案例详情进入复查对比。",
        '<a class="btn primary" href="history.html">查看案例</a>',
      );
      return;
    }
    const photos = [
      ...(c.image
        ? [
            {
              id: "original",
              date: c.capturedAt || c.createdAt,
              image: c.image,
              note: c.symptoms,
              label: "首次现场记录",
            },
          ]
        : []),
      ...(c.followups || [])
        .filter((f) => f.image)
        .map((f) => ({ ...f, label: "复查：" + f.outcome })),
    ];
    root.innerHTML =
      heading(
        "FOLLOW-UP COMPARISON",
        "对照症状，也对照期间的措施。",
        "照片变化、用户反馈与模型判断分别保存，不根据像素差异自动判定药效。",
        `<a class="btn" href="${caseLink(c)}">返回案例</a><button class="btn primary" data-care="followup" data-id="${esc(c.id)}">${icon("plus")} 提交新复查</button>`,
      ) +
      `<section class="panel care-detail-panel"><label>选择异常案例<select id="compareClinicalCase">${all()
        .map(
          (x) =>
            `<option value="${esc(x.id)}" ${x.id === id ? "selected" : ""}>${esc(x.title)}</option>`,
        )
        .join(
          "",
        )}</select></label></section>${photos.length < 2 ? `<section class="panel mt">${Z.empty("还需要两次带照片的现场记录", "先补充复查照片，记录期间措施以及实际观察到的变化。", `<button class="btn soft" data-care="followup" data-id="${esc(c.id)}">提交复查照片</button>`)}</section>` : `<section class="panel mt care-detail-panel"><div class="form-grid"><label>较早记录<select id="careBefore">${photos.map((p, i) => `<option value="${esc(p.id)}" ${i === 0 ? "selected" : ""}>${fmt(p.date)} · ${esc(p.label)}</option>`).join("")}</select></label><label>较近记录<select id="careAfter">${photos.map((p, i) => `<option value="${esc(p.id)}" ${i === photos.length - 1 ? "selected" : ""}>${fmt(p.date)} · ${esc(p.label)}</option>`).join("")}</select></label></div><div id="careComparison"></div></section>`}`;
    document.getElementById("compareClinicalCase").onchange = (e) => {
      location.href = `compare.html?clinicalId=${encodeURIComponent(e.target.value)}`;
    };
    if (photos.length >= 2) {
      const draw = () => {
        const a = photos.find(
            (p) => p.id === document.getElementById("careBefore").value,
          ),
          b = photos.find(
            (p) => p.id === document.getElementById("careAfter").value,
          );
        const area = document.getElementById("careComparison");
        if (a.id === b.id) {
          area.innerHTML =
            '<div class="notice amber mt">请选择两条不同记录。</div>';
          return;
        }
        if (a.date > b.date) {
          area.innerHTML =
            '<div class="notice amber mt">请将较早记录放在左侧。</div>';
          return;
        }
        area.innerHTML = `<div class="toolbar"><h3>两次现场记录</h3><div class="segmented"><button data-care="compare-mode" data-value="并排对比" class="${compareMode === "并排对比" ? "active" : ""}">并排对比</button><button data-care="compare-mode" data-value="滑动对比" class="${compareMode === "滑动对比" ? "active" : ""}">滑动对比</button></div></div>${compareMode === "并排对比" ? `<div class="comparison-images">${[a, b].map((p) => `<figure class="comparison-shot"><img src="${Z.safeImage(p.image)}" alt="${esc(p.label)}"><figcaption>${fmt(p.date)}<span>${esc(p.label)}</span></figcaption></figure>`).join("")}</div>` : `<div class="slider-compare"><img src="${Z.safeImage(b.image)}" alt="较近记录"><div class="slider-top" id="careSliderTop"><img src="${Z.safeImage(a.image)}" alt="较早记录"></div><div class="slider-divider" id="careSliderDivider"><span>↔</span></div></div><label class="range-control">拖动比较<input type="range" id="careSlider" min="0" max="100" value="50" aria-label="调整复查照片显示比例"></label>`}<div class="comparison-notes">${[a, b].map((p) => `<div><h3>${esc(p.label)}</h3><p class="care-paragraph">${esc(p.note)}</p></div>`).join("")}</div><div class="notice amber mt">${icon("image")}<span>${c.demo ? "初始照片为界面示意，不代表真实病斑。" : ""}采样位置、光照及期间措施需要一起核对；用户反馈不等于已确认疗效。</span></div><h3 class="mt">期间实际措施</h3>${actionsHTML(c)}<form id="careComparisonNote"><label class="mt">我的对比记录<textarea name="note" required rows="3" maxlength="2000" placeholder="记录看到的变化、拍摄条件和仍不能判断的情况。"></textarea></label><button class="btn primary mt">保存对比记录</button></form>`;
        document.getElementById("careComparisonNote").onsubmit = (e) => {
          e.preventDefault();
          const note = new FormData(e.target).get("note").trim();
          if (!note) return;
          if (
            update(c.id, (x) =>
              event(
                x,
                "人工对比笔记",
                `${fmt(a.date)} → ${fmt(b.date)}：${note}`,
              ),
            )
          ) {
            e.target.reset();
            Z.toast("对比笔记已保存到案例处理过程");
          }
        };
        const slider = document.getElementById("careSlider");
        if (slider)
          slider.oninput = () => {
            document.getElementById("careSliderTop").style.clipPath =
              `inset(0 ${100 - slider.value}% 0 0)`;
            document.getElementById("careSliderDivider").style.left =
              slider.value + "%";
          };
      };
      document.getElementById("careBefore").onchange = draw;
      document.getElementById("careAfter").onchange = draw;
      root._careDraw = draw;
      draw();
    }
  }
  function refresh() {
    window.dispatchEvent(new Event("zm:refresh"));
    if (
      document.body.dataset.page === "diagnosis" &&
      document.getElementById("clinicalResult")
    )
      document.getElementById("clinicalResult").innerHTML =
        resultPanel(currentCase());
  }
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-care]");
    if (!el) return;
    const a = el.dataset.care,
      id = el.dataset.id;
    if (a === "filter") {
      historyFilter = el.dataset.value;
      refresh();
    }
    if (a === "tab") {
      detailTab = el.dataset.value;
      refresh();
    }
    if (a === "evidence") evidence();
    if (a === "export") exportCase(id);
    if (a === "action") actionDialog(id);
    if (a === "schedule") schedule(id);
    if (a === "followup") followup(id);
    if (a === "archive")
      Z.modal(
        get(id)?.archived ? "重新打开跟踪？" : "结束本轮跟踪并归档？",
        '<p class="form-intro">只改变跟踪状态，保留调查、核验与实际措施。不代表病虫害已经治愈。</p>',
        () => {
          if (
            update(id, (c) => {
              c.archived = !c.archived;
              event(
                c,
                "跟踪状态",
                c.archived ? "用户结束本轮跟踪并归档" : "用户重新打开跟踪",
              );
            })
          ) {
            Z.closeModal();
            refresh();
          }
        },
        { submit: "确认" },
      );
    if (a === "sample-registration") {
      const s = snapshots[el.dataset.number],
        form = document.getElementById("registrationForm");
      form.elements.number.value = el.dataset.number;
      if (el.dataset.number !== "DEMO-MISMATCH-001") {
        form.elements.crop.value = s.crop;
        form.elements.target.value = s.target;
      } else {
        form.elements.crop.value = "冬小麦";
        form.elements.target.value = "白粉病";
      }
      form.requestSubmit();
    }
    if (a === "label-preview") evidence();
    if (a === "compare-mode") {
      compareMode = el.dataset.value;
      Z.root._careDraw?.();
    }
  });
  function pending() {
    return all().filter(
      (c) => !c.archived && c.proposedDate && !c.followupDone,
    );
  }
  function notifications() {
    Z.modal(
      "待复查案例",
      pending()
        .map(
          (c) =>
            `<a class="notification-item" href="${caseLink(c)}">${icon("calendar")}<span><strong>${esc(c.title)}</strong><small>${fmt(c.proposedDate)} · ${esc(c.followupNote || c.missing?.[0] || "补充现场观察")}</small></span>${icon("arrow")}</a>`,
        )
        .join("") || Z.empty("暂时没有待复查安排", "复查日期需要由你确认。"),
      null,
      { cancel: "关闭" },
    );
  }
  function tasks(root) {
    root.innerHTML =
      heading(
        "CASE FOLLOW-UP",
        "带回现场的新证据。",
        "复查由用户确认，记录提交后标记本次安排已反馈；不等于已确认防治有效。",
        '<a class="btn" href="tasks.html?source=legacy">原有本地任务</a><a class="btn primary" href="history.html">选择案例安排复查</a>',
      ) +
      `<div class="notice mb">${icon("clock")}<span>以下是案例复查安排。当前仅在浏览器内保存，不会在页面关闭后发送后台提醒。</span></div><div class="care-case-grid">${
        pending()
          .map(
            (c) =>
              `<section class="panel care-detail-panel"><span class="eyebrow">${fmt(c.proposedDate)}</span><h3>${esc(c.title)}</h3><p class="care-paragraph">${esc(c.followupNote || c.missing?.[0] || "补充现场信息")}</p><div class="actions"><button class="btn primary small" data-care="followup" data-id="${esc(c.id)}">提交复查</button><button class="btn small" data-care="schedule" data-id="${esc(c.id)}">重新安排</button><a class="text-link" href="${caseLink(c)}">查看案例 ${icon("arrow")}</a></div></section>`,
          )
          .join("") ||
        Z.empty("这一轮复查安排已反馈", "可以回看案例，或确认下一次复查时间。")
      }</div>`;
  }
  Z.Care = {
    all,
    pending,
    notifications,
    get,
    card,
    currentCase,
    get activeId() {
      return activeId;
    },
    attachDiagnosis,
    photoChanged() {
      const el = document.getElementById("intakeImageNote");
      if (!el || !diagnosisState) return;
      const d = diagnosisState;
      el.innerHTML = `${icon("image")}<span>${d.imageStatus === "ready" ? "当前图片已就绪，确认提交时会保存到本次案例；不会自动形成诊断。" : d.imageStatus === "recognizing" ? "图片观察正在进行，请等待或移除图片。" : d.imageStatus === "failed" ? "当前图片观察失败，请重试或移除；不使用旧图片结果。" : "可在左侧选图，也可先提交文字资料。图片与正式调查独立。"}</span>`;
    },
    linkChat(id) {
      if (activeId)
        update(activeId, (c) => {
          c.chatId = id;
        });
    },
    render(page, root, params) {
      if (page === "dashboard") {
        dashboard(root);
        return true;
      }
      if (page === "tasks" && params.get("source") !== "legacy") {
        tasks(root);
        return true;
      }
      if (page === "medication") {
        medication(root, params);
        return true;
      }
      if (page === "case") {
        casePage(root, params);
        return true;
      }
      if (page === "history" && params.get("source") !== "backend") {
        history(root);
        return true;
      }
      if (page === "compare" && !params.has("fieldId")) {
        comparison(root, params);
        return true;
      }
      return false;
    },
  };
})();
