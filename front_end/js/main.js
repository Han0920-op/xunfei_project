(() => {
  "use strict";
  const S = window.FarmerStore,
    A = window.FarmerAssistant,
    U = window.FarmerUI,
    { esc, icon, day } = U;
  const params = new URLSearchParams(location.search),
    isHistory = document.body.dataset.screen === "history";
  const requested = params.get("record");
  const ui = {
    record: requested ? S.get(requested) : null,
    draft: "",
    photo: null,
    photoUrl: "",
    fileError: "",
    error: "",
    busy: false,
    progress: "",
    pending: null,
    pickerVersion: 0,
    photoLoading: false,
    search: "",
  };
  document.getElementById("app").innerHTML =
    `<a class="skip-link" href="#main">跳到主要内容</a><header class="site-header"><div class="header-inner"><a class="brand" href="index.html" aria-label="智麦首页"><span>${icon("wheat")}</span><b>智麦</b><small>小麦的事，一起看看</small></a><nav aria-label="主导航"><a class="${!isHistory ? "active" : ""}" ${!isHistory ? 'aria-current="page"' : ""} href="index.html">问智麦</a><a class="${isHistory ? "active" : ""}" ${isHistory ? 'aria-current="page"' : ""} href="history.html">我的记录</a></nav><button class="icon-button help-button" data-action="help" aria-label="怎么使用智麦">${icon("help")}</button></div></header><main id="main" tabindex="-1"></main><footer class="site-footer"><span>冬小麦病虫害辅助诊断 · 用药核对 · 持续复查</span><button data-action="scope">功能范围与数据说明</button></footer><input id="photoInput" class="sr-only" tabindex="-1" type="file" accept="image/jpeg,image/png,image/webp"><dialog id="dialog"></dialog><div id="toasts" aria-live="polite"></div>`;
  const root = document.getElementById("main");
  function photoHTML(p, caption = "") {
    return `<figure class="saved-photo"><img data-photo="${esc(p.id)}" alt="${esc(p.name || "现场照片")}" loading="lazy">${caption ? `<figcaption>${esc(caption)}</figcaption>` : ""}</figure>`;
  }
  function composer() {
    return `<div class="composer ${!ui.record && !ui.pending ? "home-composer" : ""}"><div class="attachment" ${ui.photo && !ui.pending ? "" : "hidden"}>${ui.photo && !ui.pending ? `<img src="${ui.photoUrl}" alt="待发送的照片"><span><strong>${esc(ui.photo.name)}</strong><small>已选好，还没发送</small></span><button class="icon-button" data-action="remove-photo" aria-label="移除待发送照片" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${icon("close")}</button>` : ""}</div>${ui.photoLoading ? '<p class="reading-photo"><span class="spinner"></span>正在读取照片…</p>' : ""}<p class="error" id="fileError" role="alert">${esc(ui.fileError)}</p><form id="messageForm"><label class="sr-only" for="messageInput">描述你看到的情况</label><textarea id="messageInput" rows="2" maxlength="4000" placeholder="直接说说情况，也可以问天气或核对手里的药…" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${ui.busy ? "" : esc(ui.draft)}</textarea><div class="composer-bottom"><button type="button" class="attach-button" data-action="photo" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${icon("camera")} ${ui.photo ? "换张照片" : "添加照片"}</button><button type="submit" id="sendButton" class="button primary" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${ui.busy ? '<span class="spinner"></span>正在处理' : "发给智麦 " + icon("arrow")}</button></div></form><p class="error" id="sendError" role="alert">${esc(ui.error)}</p>${ui.error ? '<button class="text-button" data-action="retry">重新发送</button><button class="text-button" data-action="medicine">重新核对登记号</button>' : ""}<div class="composer-caption"><span>发送后，文字和所选照片将交给服务及模型处理</span><span>Shift + Enter 换行</span></div></div>`;
  }
  function home() {
    const last = S.records().find((r) => !r.archived);
    return `<section class="welcome"><div class="welcome-tag">${icon("leaf")} 专注冬小麦，陪你找到下一步</div><h1>小麦不对劲？<br>拍一张，一起看看。</h1><p>先查清原因，再核对用药。<br class="mobile-break">直接聊，智麦会结合照片和上下文判断下一步。</p></section><div class="home-workspace"><section class="start-card"><button class="photo-start" data-action="photo"><span class="camera-badge">${icon("camera")}</span><strong>拍照看病虫害</strong><span>拍清异常部位，能拍全株更好</span><b>选择或拍摄照片 ${icon("arrow")}</b></button><div class="or-label"><span></span>也可以直接说<span></span></div>${composer()}</section><aside class="home-aside"><button class="medicine-entry" data-action="medicine"><span class="entry-icon">${icon("book")}</span><span><strong>手里的药，能不能用？</strong><small>直接发登记号，结合实际问题核对</small></span>${icon("chevron")}</button><section class="quick-questions"><h2>不知道怎么说？试试这些</h2>${["叶片发黄了，帮我看看可能的原因", "今天适不适合下地？先帮我查天气", "我想核对手里的农药"].map((t) => `<button data-action="quick" data-text="${t}">${icon("leaf")}<span>${t}</span>${icon("arrow")}</button>`).join("")}</section>${last ? `<section class="last-record"><span class="small-label">上次的问题，接着看看</span><h2>${esc(last.title)}</h2><p>${day(last.updatedAt)}${last.demo ? " · 示例过程" : ""}</p><div><a href="index.html?record=${encodeURIComponent(last.id)}">继续查看 ${icon("arrow")}</a><button data-action="open-followup" data-id="${esc(last.id)}">拍照复查</button></div></section>` : `<section class="simple-promise">${icon("history")}<div><strong>这次的问题，会帮你记着</strong><p>下次带照片回来，<br>就能对照之前的情况继续看。</p></div></section>`}</aside></div>`;
  }
  const actionButton = (action, text, ic, primary = false) =>
    `<button class="${primary ? "button primary" : "button secondary"}" data-action="${action}" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${ic ? icon(ic) : ""}${text}</button>`;
  function resultActions(m) {
    if (m.actions?.length === 1 && m.actions[0] === "summary")
      return `<div class="answer-actions">${actionButton("summary", "下载问题摘要", "download")}</div>`;
    if (m.type === "check")
      return `<div class="answer-actions">${actionButton("label", "拍清标签", "camera", true)}${actionButton("medicine", "重新核对登记号", "book")}${actionButton("summary", "请农技人员帮看", "download")}</div>`;
    return `<div class="answer-actions">${actionButton("photo", "补拍一张照片", "camera", true)}${actionButton("medicine", "核对手里的药", "book")}</div>`;
  }
  const toolTitle = (name) =>
    ({
      get_weather: "天气查询",
      search_knowledge: "知识检索",
      check_pesticide: "登记核对",
    })[name] || "工具查询";
  function agentTraceHTML(m) {
    const vision = m.vision || [],
      tools = m.toolResults || [];
    if (!vision.length && !tools.length) return "";
    return `<details class="explanation agent-evidence"><summary>本次查看与查询依据</summary>${vision.map((v) => `<div class="knowledge-quote"><strong>图片理解 · ${v.status === "ok" ? "已返回观察" : "暂不可用"}</strong><p>${esc(v.content || "这张照片未取得可用识别结果。")}</p></div>`).join("")}${tools
      .map((t) => {
        const r = t.result || {};
        const detail =
          t.tool === "search_knowledge"
            ? knowledgeHTML(r)
            : t.tool === "check_pesticide"
              ? `${verificationHTML(r)}${labelReferenceHTML(r)}`
              : "";
        const summary =
          t.tool === "get_weather"
            ? r.status === "ok"
              ? `${r.location || ""} · ${r.source || "真实天气接口"} · ${r.report_time || r.reporttime || r.updated_at || "时间见回答"}`
              : r.message || r.note || "未取得可用天气，未用模拟结果代替。"
            : r.heading ||
              r.notice ||
              r.message ||
              r.note ||
              (r.status === "found"
                ? "检索到相关观察资料。"
                : "详见本轮回答。");
        return `<div class="knowledge-quote"><strong>${toolTitle(t.tool)}</strong><p>${esc(summary)}</p>${detail}</div>`;
      })
      .join("")}</details>`;
  }
  function knowledgeHTML(k) {
    if (!k || !k.results?.length) return "";
    return `<details class="explanation knowledge-evidence"><summary>参考了哪些资料？</summary><p>${esc(k.notice)}</p>${k.results.map((r) => `<div class="knowledge-quote"><strong>${esc(r.topic)} · ${esc(r.paragraph)}</strong><p>${esc(r.quote)}</p><small>《${esc(r.source?.title || "上传知识文档")}》 · 待农技审校</small></div>`).join("")}<p>检索时间：${esc(k.retrieved_at || "未记录")}；排序仅代表文字相关，不代表诊断概率。</p></details>`;
  }
  function verificationHTML(v) {
    if (!v) return "";
    const source = v.source;
    let link = "";
    try {
      const url = new URL(source?.url);
      if (
        url.protocol === "https:" &&
        [
          "chinapesticide.org.cn",
          "www.chinapesticide.org.cn",
          "icama.org.cn",
          "www.icama.org.cn",
          "www.moa.gov.cn",
        ].includes(url.hostname) &&
        !url.username &&
        !url.password
      )
        link = `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">打开来源核实</a>`;
    } catch (_) {}
    return `<details class="explanation"><summary>查询来源与时间</summary><p>查询时间：${esc(v.checked_at)}</p>${source ? `<p>${esc(source.title)} · 资料复核：${esc(source.reviewed_on)}</p><p>标签版本：${esc(source.label_version)} · 整理人：${esc(source.reviewer)}</p>${link}` : "<p>没有可展示的登记来源，尚未完成核验。</p>"}</details>`;
  }
  function labelReferenceHTML(v) {
    const label = v?.label_reference;
    if (!label) return "";
    let link = "";
    try {
      const url = new URL(label.url);
      if (
        url.protocol === "https:" &&
        [
          "www.moa.gov.cn",
          "www.icama.org.cn",
          "icama.org.cn",
          "www.chinapesticide.org.cn",
          "chinapesticide.org.cn",
        ].includes(url.hostname) &&
        !url.username &&
        !url.password
      )
        link = `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">打开公告版完整标签</a>`;
    } catch (_) {}
    return `<details class="explanation label-reference"><summary>核对标签限制</summary><p>${esc(label.note)}</p>${label.precautions_raw ? `<p>${esc(label.precautions_raw)}</p>` : ""}<p>版本：${esc(label.version)}；定位：${esc(label.locator || "见来源附件")}</p>${link}</details>`;
  }
  function messageHTML(m, last) {
    const photos = ui.record?.photos || [];
    const p = photos.find((x) => x.id === m.photoId);
    if (m.role === "user")
      return `<article class="message user"><div class="user-bubble">${p ? photoHTML(p) : ""}${m.text ? `<p>${esc(m.text)}</p>` : ""}</div><span class="user-avatar">我</span></article>`;
    let content = "";
    if (m.type === "agent")
      content = `<div class="agent-answer">${esc(m.text).replaceAll("\n", "<br>")}</div>${agentTraceHTML(m)}${last ? `<div class="answer-actions">${actionButton("photo", "补充照片", "camera")}${actionButton("summary", "下载问题摘要", "download")}</div>` : ""}`;
    else if (m.type === "local-note") content = `<p>${esc(m.text)}</p>`;
    else if (m.type === "question")
      content = `<p class="question-text">${esc(m.text)}</p>${m.hint ? `<p class="message-hint">${esc(m.hint)}</p>` : ""}${knowledgeHTML(m.knowledge)}`;
    else if (["result", "check", "followup-result"].includes(m.type)) {
      const before = photos.find((p) => p.id === m.beforeId),
        after = photos.find((p) => p.id === m.afterId);
      content = `<section class="answer-card ${m.tone === "danger" ? "danger" : ""}"><span class="answer-source">${esc(m.sourceLabel || (m.type === "check" ? "登记核对示例" : "示例回复 · 未识别实际图片"))}</span><h2>${esc(m.heading)}</h2><p>${esc(m.summary)}</p>${m.checks?.length ? `<dl class="label-facts">${m.checks.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>` : ""}${m.now ? `<div class="next-step"><span>${icon("arrow")} 现在可以这样做</span><p>${esc(m.now)}</p></div>` : ""}${before && after && before.id !== after.id ? `<div class="photo-pair">${photoHTML(before, "上次记录 · " + day(before.date))}${photoHTML(after, "本次补充 · " + day(after.date))}</div><p class="message-hint">位置、光照不同会影响比较，照片不能单独证明药效。</p>` : ""}${m.medicine ? `<p class="medicine-note">${icon("book")}${esc(m.medicine)}</p>` : ""}${m.explanation ? `<details class="explanation"><summary>为什么这样说？</summary><p>${esc(m.explanation)}</p></details>` : ""}${labelReferenceHTML(m.verification)}${verificationHTML(m.verification)}${knowledgeHTML(m.knowledge)}${last ? resultActions(m) : ""}</section>`;
    } else if (m.type === "legacy") {
      content = `<p>${esc(m.text)}</p><button class="text-button" data-action="old-detail">查看之前的现场记录 ${icon("chevron")}</button>${last ? `<div class="answer-actions">${actionButton("followup", "带新照片来复查", "camera", true)}${actionButton("medicine", "核对手里的药", "book")}</div>` : ""}`;
    } else
      content = `<p>${esc(m.text)}</p>${last ? `<div class="answer-actions">${actionButton("followup", "继续复查", "camera")}${actionButton("summary", "下载问题摘要", "download")}</div>` : ""}`;
    return `<article class="message assistant"><span class="assistant-avatar">${icon("wheat")}</span><div class="assistant-content"><span class="speaker">智麦 <i>·</i> ${m.type === "agent" ? "智能体" : m.type === "local-note" ? "使用提示" : m.verification ? "登记资料核对" : m.knowledge?.status === "found" ? "知识库参考" : ui.record.demo ? "交互演示" : "本地记录"}</span>${content}</div></article>`;
  }
  function pendingMessageHTML() {
    if (!ui.pending) return "";
    const p = ui.pending;
    return `<article class="message user pending-message" aria-label="本轮发送的内容"><div class="user-bubble">${p.photoUrl ? `<figure class="saved-photo"><img src="${esc(p.photoUrl)}" alt="${esc(p.photoName || "本轮照片")}"></figure>` : ""}<p>${esc(p.text || "帮我看看这张照片")}</p></div><span class="user-avatar">我</span></article>`;
  }
  function conversation() {
    const t = ui.record || {
        title: (ui.pending?.text || "照片中的小麦情况").slice(0, 36),
        createdAt: ui.pending?.createdAt,
        messages: [],
        archived: false,
        demo: false,
      },
      last = t.messages.filter((m) => m.role === "assistant").at(-1)?.id;
    return `<section class="thread-heading"><div><a class="back-link" href="history.html">${icon("back")} 我的记录</a><h1>${esc(t.title)}</h1><p>${day(t.createdAt)} · ${t.archived ? "这次跟踪已结束" : "这次的问题，会接着记"}${t.demo ? " · 此前的演示记录" : " · 智能体对话"}</p></div>${ui.record ? `<button class="icon-button" data-action="more" aria-label="这条记录的更多操作" ${ui.busy ? "disabled" : ""}>${icon("more")}</button>` : ""}</section><section class="conversation" aria-label="问题与回答"><div class="messages" role="log" aria-live="polite">${t.messages.map((m) => messageHTML(m, m.id === last)).join("")}${pendingMessageHTML()}${ui.busy ? `<div class="thinking"><span class="spinner" aria-hidden="true"></span><span id="agentProgress" role="status">${esc(ui.progress || "智麦正在结合上下文分析…")}</span></div>` : ""}</div>${t.followupDate ? `<div class="followup-date">${icon("clock")}你计划在 ${day(t.followupDate)} 再来看看 <small>日期已保存，暂不推送通知</small></div>` : ""}${t.archived ? `<div class="closed-record">这次跟踪已结束。<button class="text-button" data-action="reopen">继续跟踪</button></div>` : `${ui.record ? `<div class="followup-tools"><button data-action="action" ${ui.busy ? "disabled" : ""}>${icon("check")}记下我做了什么</button><button data-action="schedule" ${ui.busy ? "disabled" : ""}>${icon("clock")}约个时间复查</button></div>` : ""}${composer()}`}<div id="threadEnd"></div></section>`;
  }
  function recordState(t) {
    if (t.archived) return "已结束";
    if (t.followupDate) return "待复查";
    return ["distribution", "stage", "number", "target"].includes(t.step)
      ? "等你补一句"
      : "可以继续跟踪";
  }
  function history() {
    const all = S.records(),
      rs = all.filter((t) =>
        `${t.title}${t.facts?.description || ""}`.includes(ui.search),
      );
    return `<section class="records-heading"><div><span class="small-label">之前的问题，都在这里</span><h1>我的记录</h1><p>带着新照片回来，继续看看有没有变化。</p></div><a class="button primary" href="index.html">${icon("plus")}问个新问题</a></section><p class="storage-note">${icon("history")}记录和照片仅保存在当前设备，请勿清理浏览器数据。</p>${all.length > 6 ? `<label class="record-search">${icon("search")}<input id="recordSearch" placeholder="找之前的问题" value="${esc(ui.search)}" aria-label="搜索记录"></label>` : ""}<div class="record-list">${rs.map((t) => `<article class="record-row"><a class="record-main" href="index.html?record=${encodeURIComponent(t.id)}"><div class="record-thumbnail">${t.photos[0] ? `<img data-photo="${esc(t.photos[0].id)}" data-record="${esc(t.id)}" alt="此前的照片" loading="lazy">` : icon(t.kind === "medicine" ? "book" : "leaf")}</div><div><span class="record-date">${day(t.updatedAt)}${t.demo ? " · 此前的演示记录" : " · 智能体对话"}</span><h2>${esc(t.title)}</h2><p>${esc(recordState(t))}${t.followupDate ? " · " + day(t.followupDate) : ""}</p></div></a><div class="record-row-actions">${!t.archived ? `<button class="button secondary" data-action="open-followup" data-id="${esc(t.id)}">${icon("camera")}来复查</button>` : ""}<button class="icon-button" data-action="record-more" data-id="${esc(t.id)}" aria-label="管理${esc(t.title)}">${icon("more")}</button></div></article>`).join("") || `<section class="empty-records"><span>${icon("leaf")}</span><h2>${all.length ? "没找到这条记录" : "还没有记录，先从一个问题开始"}</h2><p>拍照或说说情况，智麦会帮你留住这次的观察。</p><a class="button primary" href="index.html">去问智麦 ${icon("arrow")}</a></section>`}</div>`;
  }
  function render(options = {}) {
    root.innerHTML = `${S.readError ? `<p class="storage-error" role="alert">${esc(S.readError)}</p>` : ""}${requested && !ui.record && !isHistory ? `<section class="empty-records"><h1>这条记录不在当前设备中</h1><p>可以回到我的记录重新选择。旧版服务端记录暂未在这个原型中加载。</p><a class="button primary" href="history.html">查看我的记录</a></section>` : isHistory ? history() : ui.record || ui.pending ? conversation() : home()}`;
    bind();
    hydrate();
    if (options.scroll)
      document
        .getElementById("threadEnd")
        ?.scrollIntoView({ block: "end", behavior: "instant" });
    if (options.focus)
      document.getElementById("messageInput")?.focus({ preventScroll: true });
  }
  function bind() {
    const f = document.getElementById("messageForm");
    if (f)
      f.onsubmit = (e) => {
        e.preventDefault();
        send();
      };
    const input = document.getElementById("messageInput");
    if (input) {
      input.oninput = () => {
        ui.draft = input.value;
      };
      input.onkeydown = (e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          send();
        }
      };
    }
    const search = document.getElementById("recordSearch");
    if (search)
      search.oninput = () => {
        const pos = search.selectionStart;
        ui.search = search.value;
        render();
        const n = document.getElementById("recordSearch");
        n.focus();
        n.setSelectionRange(pos, pos);
      };
    const drop =
      document.querySelector(".start-card") ||
      document.querySelector(".composer");
    if (drop) {
      drop.ondragover = (e) => {
        e.preventDefault();
        drop.classList.add("dragging");
      };
      drop.ondragleave = () => drop.classList.remove("dragging");
      drop.ondrop = (e) => {
        e.preventDefault();
        drop.classList.remove("dragging");
        if (!ui.busy && e.dataTransfer.files[0])
          choosePhoto(e.dataTransfer.files[0]);
      };
    }
  }
  async function hydrate() {
    for (const img of root.querySelectorAll("img[data-photo]")) {
      const record = img.dataset.record ? S.get(img.dataset.record) : ui.record;
      const p = record?.photos.find((p) => p.id === img.dataset.photo);
      if (!p) continue;
      try {
        const url = await S.photoUrl(p);
        if (img.isConnected) img.src = url;
      } catch {
        if (img.isConnected) {
          img.hidden = true;
          const text = document.createElement("span");
          text.className = "photo-unavailable";
          text.textContent = "照片暂时读不到";
          img.after(text);
        }
      }
    }
  }
  function clearPhoto() {
    ui.pickerVersion++;
    if (ui.photoUrl) URL.revokeObjectURL(ui.photoUrl);
    ui.photo = null;
    ui.photoUrl = "";
    ui.fileError = "";
    ui.photoLoading = false;
    document.getElementById("photoInput").value = "";
  }
  async function choosePhoto(file) {
    if (ui.busy) return;
    const version = ++ui.pickerVersion;
    if (ui.photoUrl) URL.revokeObjectURL(ui.photoUrl);
    ui.photo = null;
    ui.photoUrl = "";
    ui.photoLoading = false;
    if (
      !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
      !file.size
    ) {
      ui.fileError = "请选择一张 JPG、PNG 或 WEBP 照片。";
      render();
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      ui.fileError = "这张照片超过 10 MB，请换一张稍小的。";
      render();
      return;
    }
    ui.photoLoading = true;
    ui.fileError = "";
    render();
    const url = URL.createObjectURL(file);
    try {
      await new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = resolve;
        im.onerror = () => reject(new Error("照片没有读成功，请重新选择。"));
        im.src = url;
      });
      if (version !== ui.pickerVersion) {
        URL.revokeObjectURL(url);
        return;
      }
      if (ui.photoUrl) URL.revokeObjectURL(ui.photoUrl);
      ui.photo = file;
      ui.photoUrl = url;
      ui.photoLoading = false;
      ui.fileError = "";
      ui.error = "";
      render();
    } catch (e) {
      URL.revokeObjectURL(url);
      if (version === ui.pickerVersion) {
        ui.fileError = e.message;
        ui.photoLoading = false;
        render();
      }
    }
  }
  async function send(choice) {
    if (ui.busy || ui.photoLoading) return;
    const text = typeof choice === "string" ? choice : ui.draft.trim();
    if (!text && !ui.photo) {
      document.getElementById("messageInput")?.focus();
      return;
    }
    ui.retryChoice = typeof choice === "string" ? choice : undefined;
    ui.busy = true;
    ui.pending = {
      text,
      photoUrl: ui.photoUrl,
      photoName: ui.photo?.name,
      createdAt: new Date().toISOString(),
    };
    ui.error = "";
    ui.progress = ui.photo ? "正在发送照片，准备图片理解…" : "正在联系智麦…";
    render({ scroll: Boolean(ui.record) });
    let savedPhoto = null;
    try {
      if (ui.photo) savedPhoto = await S.putPhoto(ui.photo);
      const next = await A.respond(ui.record, {
        text,
        photo: savedPhoto,
        file: ui.photo,
        onProgress: (message) => {
          ui.progress = message;
          const progress = document.getElementById("agentProgress");
          if (progress) progress.textContent = message;
        },
        choice: typeof choice === "string",
      });
      S.save(next);
      ui.record = next;
      ui.draft = "";
      clearPhoto();
      window.history.replaceState(
        null,
        "",
        `index.html?record=${encodeURIComponent(next.id)}`,
      );
    } catch (err) {
      if (savedPhoto) await S.deletePhoto(savedPhoto.id).catch(() => {});
      ui.error = err.message || "这次没完成，内容还在，请重试。";
    } finally {
      ui.busy = false;
      ui.pending = null;
      ui.progress = "";
      render({ scroll: Boolean(ui.record) });
    }
  }
  function saveTransition(next) {
    try {
      S.save(next);
      ui.record = next;
      window.history.replaceState(
        null,
        "",
        `index.html?record=${encodeURIComponent(next.id)}`,
      );
      render({ scroll: true });
      return true;
    } catch (err) {
      ui.error = err.message;
      render();
      return false;
    }
  }
  function startMedicine(labelPhoto = false) {
    if (isHistory) {
      location.href = "index.html?intent=medicine";
      return;
    }
    const next = A.startMedicine(ui.record);
    if (saveTransition(next)) {
      ui.draft = "我想核对手里的药：";
      render({ focus: true });
      if (labelPhoto) document.getElementById("photoInput").click();
    }
  }
  function startFollowup(record = ui.record, pick = false) {
    if (!record) return;
    if (isHistory) {
      location.href = `index.html?record=${encodeURIComponent(record.id)}&followup=1`;
      return;
    }
    if (saveTransition(A.startFollowup(record))) {
      ui.draft = "我来复查这次的问题，现在的情况是：";
      render({ focus: true });
      if (pick) document.getElementById("photoInput").click();
    }
  }
  function chooseDate() {
    U.modal(
      "你想什么时候再来看？",
      `<label>复查日期<input type="date" name="date" required min="${S.date()}" value="${esc(ui.record.followupDate || "")}"></label><p class="dialog-note">日期会保存在这条记录里，当前原型不会主动推送提醒。</p>`,
      (fd) => {
        const next = structuredClone(ui.record);
        next.followupDate = fd.get("date");
        S.save(next);
        ui.record = next;
        U.close();
        render();
        U.toast("复查日期已记下");
      },
      "记下这个日期",
    );
  }
  function actualAction() {
    U.modal(
      "这期间，你做了什么？",
      `<label class="sr-only" for="actionText">实际采取的措施</label><textarea id="actionText" name="note" required maxlength="2000" rows="4" placeholder="比如：暂时没处理；补拍了照片；或记录实际用过的产品与操作。"></textarea><p class="dialog-note">按实际情况填写，不清楚的别猜。这里不会自动判断用药是否合规。</p>`,
      (fd) => {
        const note = fd.get("note").trim();
        if (!note) throw new Error("写一句实际情况就可以。");
        const next = structuredClone(ui.record);
        next.actions.push({
          id: S.id(),
          date: S.date(),
          note,
          userConfirmed: true,
        });
        next.messages.push({
          id: S.id(),
          role: "user",
          text: "处理记录：" + note,
        });
        next.messages.push({
          id: S.id(),
          role: "assistant",
          type: "note",
          text: "记下了。之后带新照片回来，可以结合这次操作继续看。",
        });
        next.updatedAt = new Date().toISOString();
        S.save(next);
        ui.record = next;
        U.close();
        render({ scroll: true });
      },
      "记下来",
    );
  }
  function downloadSummary(record = ui.record) {
    if (!record) return;
    const text = [
      `智麦 · ${record.title}`,
      `建立日期：${day(record.createdAt)}`,
      `来源：${record.demo ? "此前演示资料；不能作为实际诊断" : "智能体对话和用户现场记录；非确诊或处方"}`,
      `问题：${record.facts?.description || record.title}`,
      `分布：${record.facts?.distribution || "未确认"}；生育期：${record.facts?.stage || "未确认"}`,
      record.facts?.registration
        ? `待核对登记号：${record.facts.registration}；防治对象：${record.facts.target || "未确认"}`
        : "",
      ...record.messages
        .filter((m) => m.verification)
        .map((m) => {
          const v = m.verification;
          return `登记快照核对：${v.registration_number} / ${v.crop} / ${v.target}\n${v.heading}\n${v.summary}\n查询：${v.checked_at}\n来源：${v.source?.url || "资料不可用"}\n资料复核：${v.source?.reviewed_on || "无"}\n判断：${v.use_decision || "未确认"}\n下一步：${(v.next_steps || []).join("；")}\n标签来源：${v.label_reference?.url || "未提供"}\n${v.explanation}`;
        }),
      ...record.messages
        .filter((m) => m.knowledge?.results?.length)
        .flatMap((m) =>
          m.knowledge.results.map(
            (r) =>
              `知识参考（待审校）：${r.topic} / ${r.paragraph} / ${r.source?.title}\n${r.quote}\n文档SHA256：${r.source?.docx_sha256 || "未记录"}`,
          ),
        ),
      ...record.messages
        .filter((m) => m.type === "agent")
        .map(
          (m) =>
            `智麦回答：${m.text}\n${(m.toolResults || []).map((t) => `${toolTitle(t.tool)}：${JSON.stringify(t.result)}`).join("\n")}`,
        ),
      ...record.actions.map((a) => `实际处理 ${a.date}：${a.note}`),
      ...record.followups.map(
        (f) => `复查 ${f.date}：${f.outcome} ${f.note || ""}`,
      ),
      `照片 ${record.photos.length} 张（本文件不包含照片，请另行提供）`,
      "本摘要不代表确诊或用药处方。",
    ]
      .filter(Boolean)
      .join("\n\n");
    const url = URL.createObjectURL(
      new Blob([text], { type: "text/plain;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `智麦-${record.title.replace(/[\\/:*?"<>|]/g, "").slice(0, 40)}-问题摘要.txt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    U.toast("文字摘要已下载，照片请另外提供");
  }
  function more(record = ui.record) {
    U.modal(
      "管理这次记录",
      `<div class="record-menu"><button data-action="download-record" data-id="${esc(record.id)}">${icon("download")}下载文字摘要</button><button data-action="archive-record" data-id="${esc(record.id)}">${icon("check")}${record.archived ? "继续这次跟踪" : "结束这次跟踪"}</button><button class="remove-action" data-action="remove-record" data-id="${esc(record.id)}">${icon("close")}移出我的记录</button></div><p class="dialog-note">结束跟踪只表示你暂时结束观察，不代表已经治愈。</p>`,
    );
  }
  function remove(record) {
    U.modal(
      "移出我的记录？",
      `<p>这条问题将从列表中移除。请先下载你需要保留的文字摘要。</p>${record.legacyId ? '<p class="dialog-note">旧版原始资料会保留，不会因本次界面更新被覆盖。</p>' : ""}`,
      () => {
        S.remove(record.id);
        U.close();
        if (!isHistory) location.href = "history.html";
        else render();
      },
      "确认移出",
    );
  }
  function scope() {
    U.modal(
      "功能范围与数据说明",
      `<p>现在可以直接与智麦对话。发送照片后会调用图片理解，再由智能体结合已知情况选择回答、补问、检索知识或调用天气、登记核对工具。不会固定要求你回答发生范围或生育期。</p><p>点击发送才会把本次文字和所选照片交给后端及讯飞模型处理。本机仍保存照片与记录；当前没有云端记录同步或主动提醒。没有配置模型或服务不可用时会明确报错，不会用演示回复代替。</p><p>天气查询需要明确地点和可用接口，失败不会替换成模拟天气。登记资料来自20条公告记录，当前状态与到期日待核实，不能把范围相符当成现在可以施药。知识资料待农技审校，图片与模型回答也不等于确诊。</p><p class="dialog-note">更换设备或清理浏览器数据可能无法读取本机资料；重要记录请下载文字摘要。</p>`,
    );
  }
  function oldDetail() {
    const c = S.oldDetail(ui.record.legacyId);
    if (!c) return;
    U.modal(
      "此前保存的现场记录",
      `<p class="small-label">${day(c.createdAt)} · ${c.demo ? "原演示记录" : "用户资料"}</p><p>${esc(c.symptoms || "暂无文字描述")}</p><dl class="old-details"><dt>地区</dt><dd>${esc(c.region || "未记录")}</dd><dt>生育期</dt><dd>${esc(c.stage || "未确认")}</dd><dt>调查情况</dt><dd>${esc(c.extent || "未调查")}</dd></dl>${(c.actions || []).map((a) => `<p>${esc(a.date)}：${esc(a.note)}</p>`).join("")}<p class="dialog-note">原始资料仍保留。旧版判断不自动成为新的确诊或用药结论。</p>`,
    );
  }
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-action]");
    if (!b) return;
    const action = b.dataset.action;
    if ((ui.busy || ui.photoLoading) && !["help", "scope"].includes(action))
      return;
    const record = b.dataset.id ? S.get(b.dataset.id) : ui.record;
    if (action === "photo") document.getElementById("photoInput").click();
    if (action === "remove-photo") {
      clearPhoto();
      render();
    }
    if (action === "quick") send(b.dataset.text);
    if (action === "answer") send(b.dataset.text);
    if (action === "retry") send(ui.retryChoice);
    if (action === "medicine") startMedicine();
    if (action === "label") startMedicine(true);
    if (action === "followup") startFollowup(ui.record, true);
    if (action === "open-followup") startFollowup(record, true);
    if (action === "schedule") chooseDate();
    if (action === "action") actualAction();
    if (action === "summary" || action === "download-record")
      downloadSummary(record);
    if (action === "more" || action === "record-more") more(record);
    if (action === "old-detail") oldDetail();
    if (action === "scope") scope();
    if (action === "archive-record" || action === "reopen") {
      const next = structuredClone(record);
      next.archived = action === "reopen" ? false : !next.archived;
      try {
        S.save(next);
        if (ui.record?.id === next.id) ui.record = next;
        U.close();
        render();
        U.toast(
          next.archived ? "已结束这次跟踪，记录仍保留" : "可以继续跟踪了",
        );
      } catch (err) {
        U.toast(err.message);
      }
    }
    if (action === "remove-record") remove(record);
    if (action === "help")
      U.modal(
        "简单三步，就能开始",
        `<div class="help-step"><b>1</b><div><h3>拍张照片，或说说异常</h3><p>不用建地块档案。看不清的地方，后面再补。</p></div></div><div class="help-step"><b>2</b><div><h3>直接交流，按需补充</h3><p>智麦先结合照片与上下文判断；需要时查资料、查天气或问关键细节。</p></div></div><div class="help-step"><b>3</b><div><h3>回来复查，接着看变化</h3><p>从“我的记录”找到上次的问题，带着新照片回来。</p></div></div><button class="text-button" data-action="scope">查看能力与数据说明 ${icon("chevron")}</button>`,
      );
  });
  document.getElementById("photoInput").onchange = (e) => {
    if (e.target.files[0]) choosePhoto(e.target.files[0]);
  };
  root.addEventListener(
    "error",
    (e) => {
      if (e.target.tagName === "IMG") {
        e.target.hidden = true;
      }
    },
    true,
  );
  window.addEventListener("beforeunload", (e) => {
    if (ui.draft || ui.photo || ui.busy) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  window.addEventListener("pagehide", () => {
    if (ui.photoUrl) URL.revokeObjectURL(ui.photoUrl);
  });
  render();
  if (!isHistory && !requested && params.get("intent") === "medicine")
    startMedicine();
  if (!isHistory && ui.record && params.get("followup") === "1")
    startFollowup(ui.record);
})();
