(() => {
  "use strict";
  const Z = window.ZM,
    { icon, esc, badge, fmt, briefDate } = Z;
  const page = document.body.dataset.page;
  const params = new URLSearchParams(location.search);
  // Keep previously shared case/conversation links working after the new home page.
  if (
    page === "dashboard" &&
    (params.has("caseId") || params.has("conversationId"))
  ) {
    location.replace(`diagnosis.html${location.search}`);
    return;
  }
  Z.shell();
  const root = document.getElementById("mainContent");
  Z.root = root;
  const view = {
    fieldFilter: "全部地块",
    fieldQuery: "",
    fieldSeason: "全部种植季",
    fieldTab: "生长时间线",
    recordType: "全部",
    taskFilter: "待完成",
    taskQuery: "",
    taskField: "all",
    historyFilter: "全部",
    historyQuery: "",
    history: [],
    historyError: "",
    historyLoading: false,
    compareField: params.get("fieldId") || Z.state.fields[0]?.id,
    compareBefore: "",
    compareAfter: "",
    compareMode: "并排对比",
  };
  let historyRun = 0;
  const heading = (eyebrow, title, sub, actions = "", extra = "") =>
    `<div class="page-heading ${extra}"><div><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p>${sub}</p></div>${actions ? `<div class="actions">${actions}</div>` : ""}</div>`;
  const button = (label, ic, action, cls = "primary", extra = "") =>
    `<button class="btn ${cls}" data-action="${action}" ${extra}>${icon(ic)}${label}</button>`;
  const segment = (items, current, name) =>
    `<div class="segmented" role="group" aria-label="${esc(name)}">${items.map((t) => `<button class="${current === t ? "active" : ""}" aria-pressed="${current === t}" data-filter="${esc(name)}" data-value="${esc(t)}">${esc(t)}</button>`).join("")}</div>`;
  const tone = (f) =>
    f.attention === "持续观察"
      ? "green"
      : f.attention === "本季已结束"
        ? "gray"
        : "amber";
  function fieldCard(f) {
    const rs = Z.records(f.id);
    return `<a class="field-card" href="field.html?id=${encodeURIComponent(f.id)}"><div class="field-photo"><img src="${Z.safeImage(f.cover)}" alt="${esc(f.name)}的示意封面" loading="lazy">${badge(f.season + " 种植季", "gray")}<span class="image-disclaimer">${f.demo ? "演示档案 · 图片示意" : "封面示意图"}</span></div><div class="field-card-content"><div class="field-title"><h3>${esc(f.name)}</h3>${badge(f.attention, tone(f))}</div><p class="field-location">${icon("pin")}${esc(f.location)}</p><div class="field-info"><span>${esc(f.area)} 亩</span><span>${esc(f.variety)}</span><span>${esc(f.stage)}</span></div><div class="field-card-bottom"><span>${rs.length ? `最近记录 ${fmt(rs[0].date)}` : "等待第一条生长记录"}</span>${icon("arrow")}</div></div></a>`;
  }
  function taskRow(t, full = false) {
    const f = Z.field(t.fieldId);
    return `<div class="task-row ${t.done ? "done" : ""}"><button class="task-check ${t.done ? "done" : ""}" data-action="toggle-task" data-id="${esc(t.id)}" aria-label="${t.done ? "重新打开" : "标记完成"}：${esc(t.title)}" aria-pressed="${t.done}">${t.done ? icon("check") : ""}</button><div class="task-row-main"><button class="task-title" data-action="task-detail" data-id="${esc(t.id)}">${esc(t.title)}</button><div class="task-meta"><span>${esc(f?.name || "未关联地块")}</span><span>·</span><span>${full ? esc(t.source) : briefDate(t.date)}</span>${t.demo ? "<span>· 演示</span>" : ""}</div>${full ? `<p>${esc(t.note)}</p>` : ""}</div>${full ? `<div class="task-inline"><div class="task-date">${fmt(t.date)}<small>${t.demo ? "历史情境日期" : "计划日期"}</small></div>${badge(t.done ? "已完成" : t.priority, t.done ? "gray" : t.priority === "优先关注" ? "amber" : "green")}<button class="btn small" data-action="task-detail" data-id="${esc(t.id)}">查看详情</button></div>` : `${badge(t.priority, t.priority === "优先关注" ? "amber" : "gray")}<button class="text-link" data-action="task-detail" data-id="${esc(t.id)}">查看 ${icon("chevron")}</button>`}</div>`;
  }
  function fields() {
    const fs = Z.state.fields.filter(
      (f) =>
        (view.fieldFilter === "全部地块" || f.attention === view.fieldFilter) &&
        (view.fieldSeason === "全部种植季" || f.season === view.fieldSeason) &&
        `${f.name}${f.location}${f.variety}`
          .toLowerCase()
          .includes(view.fieldQuery.toLowerCase()),
    );
    root.innerHTML =
      heading(
        "MY FIELDS",
        "补充地块背景，让调查少问一步。",
        "保存地区、品种和现场记录，作为病虫害案例的背景。",
        button("新建地块", "plus", "new-field"),
      ) +
      `<div class="fields-summary"><span><strong>${Z.state.fields.length}</strong> 块地已建档</span><span><strong>${Z.state.records.length}</strong> 条生长记录</span><span>仅此设备保存 · 可在档案内导出</span></div><div class="toolbar">${segment(["全部地块", "持续观察", "待复查", "待补记录"], view.fieldFilter, "fieldFilter")}<div class="filter-group"><label class="filter-search">${icon("search")}<input id="fieldSearch" placeholder="搜索地块、地区或品种" aria-label="搜索地块" value="${esc(view.fieldQuery)}"></label><select id="fieldSeason" aria-label="筛选种植季"><option>全部种植季</option>${[...new Set(Z.state.fields.map((f) => f.season))].map((s) => `<option ${view.fieldSeason === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div></div><div class="section-heading"><span class="result-count">共 ${fs.length} 块地块</span></div><div class="field-grid">${fs.map(fieldCard).join("")}${!fs.length ? Z.empty("没有找到符合条件的地块", "调整筛选条件，或建立一份新的地块档案。") : ""}<button class="add-field-card" data-action="new-field">${icon("plus")}<strong>记录一块新的麦田</strong><small>从这里开始，陪伴下一季生长</small></button></div><p class="demo-note">${icon("book")}示例地块有“演示档案”标记；封面图片仅为示意，不用于判断地块长势。</p>`;
    bindInput("fieldSearch", "fieldQuery", fields);
  }
  function timelineEntry(r) {
    const date = r.date.split("-");
    return `<article class="timeline-entry"><div class="timeline-date">${Number(date[1])}.${date[2]}<small>${date[0]}</small></div><div class="timeline-entry-content">${badge(r.type, r.type === "农事" ? "blue" : r.type === "复查" ? "amber" : "green")}<h3>${esc(r.title)}</h3><p>${esc(r.note)}</p>${r.image ? `<img class="timeline-picture" src="${Z.safeImage(r.image)}" alt="${esc(r.title)}${r.demo ? "，演示照片" : ""}" loading="lazy">` : ""}<div class="timeline-foot"><span>${esc(r.stage || "生育期待记录")}</span><span>${r.demo ? "演示记录 · 图片示意" : "本地记录"}</span></div></div></article>`;
  }
  function fieldPage() {
    const id = params.get("id") || Z.state.fields[0]?.id,
      f = Z.field(id);
    if (!f) {
      root.innerHTML = Z.empty(
        "没有找到这块地的档案",
        "档案可能未保存在当前浏览器，请从我的地块重新选择。",
        '<a class="btn primary" href="fields.html">返回我的地块</a>',
      );
      return;
    }
    const rs = Z.records(id),
      tasks = Z.state.tasks.filter((t) => t.fieldId === id && !t.done);
    root.innerHTML = `<a href="fields.html" class="back-link">${icon("arrow")} 返回我的地块</a><div class="page-heading"><div><span class="eyebrow">FIELD JOURNAL · ${esc(f.season)}</span><h1>地块背景与现场记录。</h1></div><div class="actions">${button("导出文字档案", "download", "none", "", 'data-local="export-field"')}${button("记录新观察", "plus", "new-record", "primary", `data-field="${esc(id)}"`)}</div></div><section class="field-detail-hero"><div class="field-detail-copy"><div class="actions">${badge(f.attention, tone(f))}${badge(f.demo ? "历史情境示例" : "本地地块", "gray")}</div><h1>${esc(f.name)}</h1><p class="field-location">${icon("pin")}${esc(f.location)}</p><div class="field-info"><span>${esc(f.area)} 亩</span><span>${esc(f.variety)}</span><span>${esc(f.stage)}</span><span>${esc(f.season)} 季</span></div></div><div class="field-detail-photo"><img src="${Z.safeImage(f.cover)}" alt="麦田封面示意图"><span class="image-disclaimer">封面示意图</span></div></section><div class="field-detail-tabs" role="group" aria-label="档案栏目">${["生长时间线", "农事记录", "档案信息"].map((t) => `<button class="${view.fieldTab === t ? "active" : ""}" aria-pressed="${view.fieldTab === t}" data-filter="fieldTab" data-value="${t}">${t}</button>`).join("")}</div>${
      view.fieldTab === "档案信息"
        ? `<section class="panel info-panel"><div class="actions" style="justify-content:space-between"><h2>这块田的基础信息</h2><button class="btn small" data-local="edit-field">${icon("edit")} 编辑档案</button></div><dl class="detail-list"><dt>地块名称</dt><dd>${esc(f.name)}</dd><dt>所在地区</dt><dd>${esc(f.location)}</dd><dt>面积</dt><dd>${esc(f.area)} 亩</dd><dt>品种</dt><dd>${esc(f.variety)}</dd><dt>播种日期</dt><dd>${fmt(f.sowDate)}</dd><dt>种植季</dt><dd>${esc(f.season)}</dd><dt>生育期</dt><dd>${esc(f.stage)}</dd><dt>采样点与备注</dt><dd>${esc(f.note || "暂未填写")}</dd></dl><div class="notice">${icon("book")}<span>生育期及管理信息由档案记录提供，未通过现场自动监测确认。</span></div></section>`
        : `<div class="detail-columns"><section class="panel"><div class="panel-head"><div><h2>${view.fieldTab === "农事记录" ? "每一次操作，都是重要的背景" : "生长时间线"}</h2><p>${view.fieldTab === "农事记录" ? "记录实际发生的管理操作，供后续复查参考" : "观察、行动、复查，在时间里连成线"}</p></div><span class="result-count">${rs.filter((r) => view.fieldTab !== "农事记录" || r.type === "农事").length} 条记录</span></div>${view.fieldTab === "生长时间线" ? `<div style="padding:0 23px 10px">${segment(["全部", "观察", "农事", "复查"], view.recordType, "recordType")}</div>` : ""}<div class="timeline">${
            rs
              .filter((r) =>
                view.fieldTab === "农事记录"
                  ? r.type === "农事"
                  : view.recordType === "全部" || r.type === view.recordType,
              )
              .map(timelineEntry)
              .join("") ||
            Z.empty(
              "这一栏还没有记录",
              "留下第一次现场观察，或记下一次实际农事操作。",
              `<button class="btn soft" data-action="new-record" data-field="${esc(id)}">${icon("plus")} 添加记录</button>`,
            )
          }</div></section><aside class="detail-side"><section class="panel"><div class="detail-note"><h3>这一季，持续积累</h3><p>${esc(f.note || "记录固定采样点位置，便于后续在相近角度拍摄。")}</p></div><div class="mini-stat-grid"><div class="mini-stat"><strong>${rs.length}</strong><small>条生长记录</small></div><div class="mini-stat"><strong>${tasks.length}</strong><small>项待完成任务</small></div></div><div class="panel-body"><a class="btn soft" href="compare.html?fieldId=${encodeURIComponent(id)}" style="width:100%">${icon("compare")} 对比两次生长观察</a></div></section><section class="panel"><div class="panel-head"><h2>下一步关注</h2><button class="text-link" data-action="new-task" data-field="${esc(id)}">${icon("plus")} 添加</button></div>${
            tasks
              .slice(0, 3)
              .map((t) => taskRow(t))
              .join("") ||
            '<div class="panel-body muted">暂时没有待完成任务。</div>'
          }</section></aside></div>`
    }<p class="demo-note">${icon("book")}${f.demo ? "此档案包含示例记录。示例图片并非同一采样点连续实拍，不支持据此推断真实长势变化。" : "本地档案仅保存在当前浏览器，请定期导出。图片与文字记录不等同于专业检测结果。"}</p>`;
  }
  function tasks() {
    const filtered = Z.state.tasks
      .filter(
        (t) =>
          (view.taskFilter === "全部任务" ||
            (view.taskFilter === "已完成" ? t.done : !t.done)) &&
          (view.taskField === "all" || t.fieldId === view.taskField) &&
          `${t.title}${t.note}${Z.field(t.fieldId)?.name || ""}`
            .toLowerCase()
            .includes(view.taskQuery.toLowerCase()),
      )
      .sort((a, b) => a.date.localeCompare(b.date));
    const pending = Z.state.tasks.filter((t) => !t.done).length;
    root.innerHTML =
      heading(
        "FOLLOW-UP & ACTIONS",
        "让每一次建议，都有后续。",
        "把待补信息、巡田与复查变成清晰的行动，再带回新的证据。",
        button("创建跟踪任务", "plus", "new-task"),
      ) +
      `<div class="fields-summary"><span><strong>${pending}</strong> 项待完成</span><span><strong>${Z.state.tasks.length - pending}</strong> 项已完成</span><span>完成任务不等于已排除地块风险</span></div><div class="toolbar">${segment(["待完成", "已完成", "全部任务"], view.taskFilter, "taskFilter")}<div class="filter-group"><label class="filter-search">${icon("search")}<input id="taskSearch" value="${esc(view.taskQuery)}" aria-label="搜索任务" placeholder="搜索任务或地块"></label><select id="taskField" aria-label="筛选任务地块"><option value="all">全部地块</option>${Z.fieldOptions(view.taskField)}</select></div></div><section class="panel task-list">${filtered.length ? filtered.map((t) => taskRow(t, true)).join("") : Z.empty("这里暂时没有任务", "调整筛选条件，或为下一次观察安排任务。", button("创建任务", "plus", "new-task", "soft"))}</section><div class="notice mt">${icon("clock")}<span>初始任务为历史情境演示。新任务可在页面内管理；当前原型不会在浏览器关闭后自动发送通知。</span></div>`;
    bindInput("taskSearch", "taskQuery", tasks);
  }
  function compare() {
    if (!Z.field(view.compareField)) view.compareField = Z.state.fields[0]?.id;
    const f = Z.field(view.compareField);
    if (!f) {
      root.innerHTML = Z.empty(
        "先建立一份地块档案",
        "添加两次带照片的观察后，即可开始比较。",
        button("建立档案", "plus", "new-field"),
      );
      return;
    }
    const rs = Z.records(f.id)
      .filter((r) => r.image)
      .reverse();
    if (!rs.some((r) => r.id === view.compareBefore))
      view.compareBefore = rs[0]?.id || "";
    if (!rs.some((r) => r.id === view.compareAfter))
      view.compareAfter = rs[rs.length - 1]?.id || "";
    const before = rs.find((r) => r.id === view.compareBefore),
      after = rs.find((r) => r.id === view.compareAfter),
      valid =
        before && after && before.id !== after.id && before.date < after.date;
    const options = (selected) =>
      rs
        .map(
          (r) =>
            `<option value="${esc(r.id)}" ${r.id === selected ? "selected" : ""}>${fmt(r.date)} · ${esc(r.title)}</option>`,
        )
        .join("");
    root.innerHTML =
      heading(
        "GROWTH COMPARISON",
        "把变化放在一起，看得更清楚。",
        "结合拍摄条件、现场观察与期间农事，记录变化，也保留不确定性。",
        `<button class="btn" data-action="new-record" data-field="${esc(f.id)}">${icon("plus")} 补充新观察</button>`,
      ) +
      `<section class="panel compare-selectors"><label>选择地块<select id="compareField">${Z.fieldOptions(f.id)}</select></label><label>较早的一次观察<select id="compareBefore" ${rs.length ? "" : "disabled"}>${options(view.compareBefore) || "<option>暂无图片记录</option>"}</select></label><label>较近的一次观察<select id="compareAfter" ${rs.length ? "" : "disabled"}>${options(view.compareAfter) || "<option>暂无图片记录</option>"}</select></label></section>${valid ? `<section class="panel compare-stage"><div class="panel-head"><div><h2>${esc(f.name)} · 两次观察</h2><p>${fmt(before.date)} — ${fmt(after.date)} · 相隔 ${Math.round((new Date(after.date) - new Date(before.date)) / 86400000)} 天</p></div>${segment(["并排对比", "滑动对比"], view.compareMode, "compareMode")}</div>${view.compareMode === "并排对比" ? `<div class="comparison-images">${[before, after].map((r, i) => `<figure class="comparison-shot"><span class="shot-tag">${i ? "本次观察" : "上次观察"}</span><img src="${Z.safeImage(r.image)}" alt="${fmt(r.date)} ${esc(r.title)}${r.demo ? "，图片示意" : ""}"><figcaption>${fmt(r.date)}<span>${esc(r.stage || "生育期待确认")}</span></figcaption></figure>`).join("")}</div>` : `<div class="slider-compare"><img src="${Z.safeImage(after.image)}" alt="较近一次观察：${fmt(after.date)}"><div class="slider-top" id="sliderTop"><img src="${Z.safeImage(before.image)}" alt="较早一次观察：${fmt(before.date)}"></div><span class="slider-label before">${fmt(before.date)}</span><span class="slider-label after">${fmt(after.date)}</span><div class="slider-divider" id="sliderDivider"><span>↔</span></div></div><label class="range-control">拖动比较<input type="range" id="compareSlider" min="0" max="100" value="50" aria-label="调整两张照片的显示比例"><span id="sliderValue">50%</span></label>`}<div class="compare-disclaimer">${icon("book")}<span>${before.demo || after.demo ? "示例照片仅用于界面演示，并非同一采样点连续实拍。" : "照片来自本地记录，拍摄条件尚需人工确认。"}这里不会根据颜色或像素差异自动判定改善、病因或生长速度。</span></div></section><div class="comparison-notes">${[before, after].map((r, i) => `<article class="panel observation-panel"><span class="eyebrow">${i ? "LATEST OBSERVATION" : "PREVIOUS OBSERVATION"}</span><h3>${esc(r.title)}</h3><p>${esc(r.note)}</p><div class="timeline-foot"><span>${fmt(r.date)}</span>${badge(r.demo ? "演示记录" : "本地记录", "gray")}</div></article>`).join("")}</div><section class="panel compare-reflection"><h2>这次对比，你观察到了什么？</h2><p class="muted" style="font-size:11px;margin-top:6px">先确认照片是否可比，再记录变化与仍需补充的信息。</p><div class="compare-checks"><label><input type="checkbox" id="samePoint"> 同一采样点</label><label><input type="checkbox" id="sameAngle"> 角度与距离相近</label><label><input type="checkbox" id="sameLight"> 光照条件相近</label></div><label for="comparisonNote" class="sr-only">本次对比记录</label><textarea id="comparisonNote" rows="3" maxlength="4000" placeholder="哪些可见特征有变化？期间做过什么操作？还有哪些信息无法确认？"></textarea><div class="compare-save-actions"><small>保存后会加入“${esc(f.name)}”的复查时间线。</small><div class="actions"><button class="btn" data-local="compare-task">${icon("calendar")} 安排后续复查</button><button class="btn primary" data-local="save-comparison">${icon("check")} 保存对比记录</button></div></div><p id="compareError" class="form-error" role="alert"></p></section>` : `<section class="panel mt">${Z.empty(rs.length < 2 ? "还需要两次带照片的观察" : "请选择两个不同日期的观察", rs.length < 2 ? "先在地块档案中添加照片记录，让前后变化有迹可循。" : "将较早的记录放在左侧，较近的记录放在右侧。", `<button class="btn soft" data-action="new-record" data-field="${esc(f.id)}">${icon("plus")} 添加生长记录</button>`)}</section>`}`;
  }
  function demoCases() {
    const deleted = Z.state.deletedCases || [];
    return [
      {
        id: "demo-east",
        image: "assets/wheat-green.jpg",
        summary: "叶片局部偏黄，需结合分布与近期管理记录进一步判断。",
        recognition:
          "**图片可见特征（示例）**\n\n- 图中可见小麦植株与叶片。\n- 部分叶片颜色有差异，实际颜色受拍摄光照影响。\n\n单张照片不足以确定病因，不能据此判断施肥剂量。",
        diagnosis:
          "**当前判断：信息仍需补充。**\n\n请补充田间全景、异常分布和近期水肥记录，再结合生育期综合判断。",
        advice: "保持固定采样点复拍，记录期间实际发生的操作。",
        status: "进行中",
        create_time: "2026-04-18 09:30",
        conversation_id: null,
        demo: true,
        fieldId: "east",
        recheck_count: 1,
      },
      {
        id: "demo-river",
        image: "assets/wheat-gold.jpg",
        summary: "建立一次图片观察，等待确认生育期与现场情况。",
        recognition: "图片仅为麦田示意，不代表该地块真实生育期。",
        diagnosis: "",
        advice: "",
        status: "进行中",
        create_time: "2026-04-16 14:20",
        conversation_id: null,
        demo: true,
        fieldId: "river",
        recheck_count: 0,
      },
      ...Z.state.cases,
    ]
      .filter((c) => !deleted.includes(c.id))
      .map((c) => ({
        ...c,
        ...Z.state.caseLinks?.[c.id],
        status: Z.state.caseStatuses?.[c.id] || c.status,
      }));
  }
  function apiImage(path) {
    if (!path) return "";
    try {
      const base = Z.readSetting("zhimai.apiBase", "http://127.0.0.1:8000");
      const u = new URL(path, base + "/");
      return ["http:", "https:"].includes(u.protocol) ? u.href : "";
    } catch {
      return "";
    }
  }
  function history() {
    const cases = Z.mode === "demo" ? demoCases() : view.history;
    const filtered = cases.filter(
      (c) =>
        (view.historyFilter === "全部" || c.status === view.historyFilter) &&
        `${c.summary || ""}${c.id}${c.diagnosis || ""}`
          .toLowerCase()
          .includes(view.historyQuery.toLowerCase()),
    );
    root.innerHTML =
      heading(
        "DIAGNOSIS HISTORY",
        "让每一次判断，都有迹可循。",
        "回看图片观察、诊断与后续复查，继续跟踪尚未解决的问题。",
        `<button class="btn" data-local="refresh-history">${icon("refresh")} 刷新记录</button><a href="diagnosis.html" class="btn primary">${icon("plus")} 开始新诊断</a>`,
      ) +
      `<div class="notice ${Z.mode === "demo" ? "amber" : ""}">${icon("book")}<span>${Z.mode === "demo" ? "当前为演示案例及本地演示对话，不是真实模型诊断。可在顶部切换为后端连接模式。" : "当前使用后端实际历史接口。地块档案与本页诊断案例尚未自动关联。"}</span></div><div class="toolbar">${segment(["全部", "进行中", "已完成", "失败"], view.historyFilter, "historyFilter")}<label class="filter-search">${icon("search")}<input id="historySearch" placeholder="搜索案例内容或编号" aria-label="搜索历史案例" value="${esc(view.historyQuery)}"></label></div>${view.historyLoading && Z.mode === "live" ? `<section class="panel"><div class="empty-state"><span class="spinner"></span><h3 class="mt">正在读取历史记录</h3><p>等待后端实际响应。</p></div></section>` : view.historyError && Z.mode === "live" ? `<section class="panel">${Z.empty("历史记录暂时无法加载", view.historyError, `<div class="error-actions"><button class="btn primary" data-local="refresh-history">${icon("refresh")} 重试</button><button class="btn" data-action="settings">检查连接设置</button></div>`)}</section>` : `<p class="result-count mb">共 ${filtered.length} 条记录</p><div class="history-grid">${filtered.map((c) => `<button class="case-card" data-local="case-detail" data-id="${esc(c.id)}"><div class="case-image">${c.image || c.thumbnail ? `<img src="${esc(c.demo ? Z.safeImage(c.image) : apiImage(c.thumbnail || c.image))}" alt="案例 #${esc(c.id)} 的图片" loading="lazy">` : ""}${badge(c.status, c.status === "失败" ? "red" : c.status === "进行中" ? "amber" : "green")}<span class="image-disclaimer">${c.demo ? "演示案例 · 图片示意" : "用户上传图片"}</span></div><div class="case-content"><small>${esc(c.create_time)}</small><h3>${c.fieldId ? esc(Z.field(c.fieldId)?.name || "图片观察") : "小麦生长观察"} · ${c.demo ? "示例" : "案例 #" + esc(c.id)}</h3><p class="case-summary">${esc(c.summary || "暂无图片摘要")}</p><div class="case-footer"><span>查看观察与诊断</span>${icon("arrow")}</div></div></button>`).join("") || Z.empty("暂时没有符合条件的案例", "调整筛选条件，或开始一次新的图片诊断。", '<a href="diagnosis.html" class="btn soft">开始新诊断</a>')}</div>`}`;
    bindInput("historySearch", "historyQuery", history);
  }
  async function loadHistory() {
    if (Z.mode === "demo") {
      history();
      Z.toast("演示记录已刷新");
      return;
    }
    const run = ++historyRun;
    view.historyLoading = true;
    view.historyError = "";
    history();
    try {
      const result = await window.ZhimaiAPI.getHistoryList();
      if (run !== historyRun) return;
      if (!Array.isArray(result)) throw new Error("历史接口返回格式不正确。");
      view.history = result;
    } catch (err) {
      if (run !== historyRun) return;
      view.historyError = err.message || "无法连接后端，请检查服务与连接地址。";
    } finally {
      if (run === historyRun) {
        view.historyLoading = false;
        history();
      }
    }
  }
  async function caseDetail(id) {
    let c;
    if (Z.mode === "demo")
      c = demoCases().find((c) => String(c.id) === String(id));
    else {
      const d = Z.modal(
        "读取案例详情",
        '<div class="empty-state"><span class="spinner"></span><p>正在读取实际诊断记录…</p></div>',
        null,
        { cancel: "关闭" },
      );
      try {
        c = await window.ZhimaiAPI.getCaseDetail(id);
        if (!d.open) return;
      } catch (err) {
        if (d.open)
          d.querySelector(".modal-body").innerHTML =
            `<div class="notice error">${icon("alert")}<span>${esc(err.message)}</span></div><button class="btn mt" data-local="case-detail" data-id="${esc(id)}">重试</button>`;
        return;
      }
    }
    if (!c) return;
    const md = window.ZM.markdown || esc;
    const detail = `<div class="case-detail-top">${c.image ? `<img src="${esc(c.demo ? Z.safeImage(c.image) : apiImage(c.image))}" alt="本次案例图片">` : '<div class="empty-state">暂无图片</div>'}<div>${badge(c.status, c.status === "失败" ? "red" : c.status === "进行中" ? "amber" : "green")}<dl class="detail-list"><dt>创建时间</dt><dd>${esc(c.create_time)}</dd><dt>复查次数</dt><dd>${Number(c.recheck_count) || 0}</dd><dt>最近复查</dt><dd>${esc(c.last_recheck_time || "暂无")}</dd><dt>数据来源</dt><dd>${c.demo ? "演示情境" : "后端实际记录"}</dd></dl></div></div>${[
      ["图片可见特征", c.recognition || c.summary],
      ["诊断结论", c.diagnosis],
      ["管理建议", c.advice],
    ]
      .map(
        ([t, text]) =>
          `<section class="case-section"><h3>${t}</h3><div class="rich-text">${Z.mode === "live" && t !== "图片可见特征" ? '<p class="muted">此字段来自原有自由文本模型，尚未完成结构化来源与用药审核，不在这里展示为可执行方案。</p>' : text ? md(text) : '<p class="muted">暂无独立内容，等待实际诊断结果。</p>'}</div></section>`,
      )
      .join(
        "",
      )}<div class="actions mt"><button class="btn danger small" data-local="delete-case" data-id="${esc(c.id)}">${icon("trash")} 删除案例</button>${c.status === "进行中" ? `<button class="btn soft small" data-local="finish-case" data-id="${esc(c.id)}">${icon("check")} 结束跟踪</button>` : ""}<a class="btn primary small" href="diagnosis.html?caseId=${encodeURIComponent(c.id)}${c.conversation_id ? "&conversationId=" + encodeURIComponent(c.conversation_id) : ""}">${icon("refresh")} 继续对话与复查</a>${c.fieldId ? `<a class="btn small" href="field.html?id=${encodeURIComponent(c.fieldId)}">查看地块档案</a>` : ""}</div>`;
    Z.modal(c.demo ? "观察与诊断 · 演示案例" : `案例 #${c.id}`, detail, null, {
      wide: true,
      cancel: "关闭",
    });
  }
  function bindInput(id, key, renderFn) {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener("input", () => {
      const pos = input.selectionStart;
      view[key] = input.value;
      renderFn();
      const next = document.getElementById(id);
      next?.focus();
      try {
        next?.setSelectionRange(pos, pos);
      } catch {}
    });
  }
  function updateCounts() {
    const count = Z.Care
      ? Z.Care.pending().length
      : Z.state.tasks.filter((t) => !t.done).length;
    document.querySelector(".nav-count").textContent = count;
    document.querySelector(".notification-dot").hidden = count === 0;
  }
  function render() {
    updateCounts();
    if (Z.Care?.render(page, root, params)) return;
    if (page === "fields") fields();
    if (page === "field") fieldPage();
    if (page === "tasks") tasks();
    if (page === "compare") compare();
    if (page === "history") history();
  }
  document.querySelector(".menu-toggle").onclick = () => {
    const open = document.body.classList.toggle("nav-open");
    document
      .querySelector(".menu-toggle")
      .setAttribute("aria-expanded", String(open));
  };
  document.querySelector(".sidebar-scrim").onclick = () => {
    document.body.classList.remove("nav-open");
    document
      .querySelector(".menu-toggle")
      .setAttribute("aria-expanded", "false");
  };
  window.addEventListener("zm:refresh", render);
  document.addEventListener("click", async (e) => {
    const filter = e.target.closest("[data-filter]");
    if (filter) {
      view[filter.dataset.filter] = filter.dataset.value;
      render();
      return;
    }
    const el = e.target.closest("[data-local]");
    if (!el) return;
    const a = el.dataset.local,
      id = el.dataset.id;
    const fieldId = params.get("id") || Z.state.fields[0]?.id;
    if (a === "weather-info")
      Z.modal(
        "天气数据说明",
        `<div class="notice amber">${icon("sun")}<span>本卡片是 2026 年 4 月 18 日的历史情境示意，温度、风力、湿度均为演示值，未连接实时天气服务。</span></div><p class="form-intro mt">诊断页在连接后端时，可展示天气工具实际返回的来源。工具返回“模拟”时会保留该标记；预报不等同于田间实测。</p>`,
        null,
        { cancel: "知道了" },
      );
    if (a === "edit-field") Z.newField(fieldId);
    if (a === "export-field") Z.exportField(fieldId);
    if (a === "compare-task")
      Z.newTask(
        view.compareField,
        "完成下一轮固定点位复查",
        "保持相近采样位置、角度和光照，补充仍待确认的信息。",
      );
    if (a === "save-comparison") {
      const text = document.getElementById("comparisonNote").value.trim();
      if (!text) {
        document.getElementById("compareError").textContent =
          "请先写下这次观察到的变化或仍需确认的信息。";
        return;
      }
      const conditions = [
        ["samePoint", "同一采样点"],
        ["sameAngle", "角度与距离相近"],
        ["sameLight", "光照条件相近"],
      ]
        .filter(([id]) => document.getElementById(id).checked)
        .map((x) => x[1]);
      const r = {
        id: Z.uid(),
        fieldId: view.compareField,
        date: Z.today(),
        type: "复查",
        title: "两次观察的对比记录",
        note: `对比记录：${Z.records(view.compareField).find((r) => r.id === view.compareBefore)?.date} → ${Z.records(view.compareField).find((r) => r.id === view.compareAfter)?.date}\n已确认拍摄条件：${conditions.join("、") || "尚未确认"}\n\n${text}`,
        stage: Z.field(view.compareField)?.stage || "",
        demo: false,
      };
      if (Z.commit((s) => s.records.push(r))) {
        document.getElementById("comparisonNote").value = "";
        document.getElementById("compareError").textContent = "";
        Z.toast("对比记录已加入地块的复查时间线");
      }
    }
    if (a === "refresh-history") loadHistory();
    if (a === "case-detail") caseDetail(id);
    if (a === "finish-case") {
      if (Z.mode === "demo") {
        if (
          Z.commit((s) => {
            s.caseStatuses ??= {};
            s.caseStatuses[id] = "已完成";
          })
        ) {
          Z.closeModal();
          history();
          Z.toast("已结束此演示案例的跟踪");
        }
      } else {
        el.disabled = true;
        try {
          await window.ZhimaiAPI.finishCase(id);
          Z.closeModal();
          await loadHistory();
          Z.toast("案例跟踪已结束");
        } catch (err) {
          Z.toast(err.message, "error");
          el.disabled = false;
        }
      }
    }
    if (a === "delete-case")
      Z.modal(
        "删除这条诊断案例？",
        `<p class="form-intro">${Z.mode === "demo" ? "将从当前浏览器的演示历史中移除此案例。" : "将删除该案例及其复查记录和相关图片。"}关联聊天记录与地块档案不会被删除。</p>`,
        async () => {
          if (Z.mode === "demo") {
            if (
              !Z.commit((s) => {
                s.deletedCases ??= [];
                s.deletedCases.push(id);
              })
            )
              return;
          } else await window.ZhimaiAPI.deleteCase(id);
          Z.closeModal();
          if (Z.mode === "demo") history();
          else await loadHistory();
          Z.toast("案例已删除");
        },
        { submit: "确认删除" },
      );
  });
  root.addEventListener("change", (e) => {
    if (e.target.id === "fieldSeason") {
      view.fieldSeason = e.target.value;
      fields();
    }
    if (e.target.id === "taskField") {
      view.taskField = e.target.value;
      tasks();
    }
    if (e.target.id === "compareField") {
      view.compareField = e.target.value;
      view.compareBefore = "";
      view.compareAfter = "";
      compare();
    }
    if (e.target.id === "compareBefore") {
      view.compareBefore = e.target.value;
      compare();
    }
    if (e.target.id === "compareAfter") {
      view.compareAfter = e.target.value;
      compare();
    }
  });
  root.addEventListener("input", (e) => {
    if (e.target.id === "compareSlider") {
      document.getElementById("sliderTop").style.clipPath =
        `inset(0 ${100 - Number(e.target.value)}% 0 0)`;
      document.getElementById("sliderDivider").style.left =
        `${e.target.value}%`;
      document.getElementById("sliderValue").textContent = e.target.value + "%";
    }
  });
  root.addEventListener(
    "error",
    (e) => {
      if (e.target.tagName === "IMG") {
        e.target.hidden = true;
        const p = document.createElement("span");
        p.className = "muted";
        p.textContent = "图片暂时无法显示";
        p.style.cssText =
          "display:grid;place-items:center;height:100%;font-size:11px";
        e.target.after(p);
      }
    },
    true,
  );
  render();
  if (
    page === "history" &&
    params.get("source") === "backend" &&
    Z.mode === "live"
  )
    loadHistory();
  Z.page = page;
  Z.root = root;
  Z.caseDetail = caseDetail;
  Z.demoCases = demoCases;
})();
