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
    pickerVersion: 0,
    photoLoading: false,
    search: "",
  };
  document.getElementById("app").innerHTML =
    `<a class="skip-link" href="#main">跳到主要内容</a><header class="site-header"><div class="header-inner"><a class="brand" href="index.html" aria-label="智麦首页"><span>${icon("wheat")}</span><b>智麦</b><small>小麦的事，一起看看</small></a><nav aria-label="主导航"><a class="${!isHistory ? "active" : ""}" ${!isHistory ? 'aria-current="page"' : ""} href="index.html">问智麦</a><a class="${isHistory ? "active" : ""}" ${isHistory ? 'aria-current="page"' : ""} href="history.html">我的记录</a></nav><button class="icon-button help-button" data-action="help" aria-label="怎么使用智麦">${icon("help")}</button></div></header><main id="main" tabindex="-1"></main><footer class="site-footer"><span>冬小麦病虫害辅助诊断 · 用药核对 · 持续复查</span><button data-action="scope">交互演示，非真实诊断</button></footer><input id="photoInput" class="sr-only" tabindex="-1" type="file" accept="image/jpeg,image/png,image/webp"><dialog id="dialog"></dialog><div id="toasts" aria-live="polite"></div>`;
  const root = document.getElementById("main");
  function photoHTML(p, caption = "") {
    return `<figure class="saved-photo"><img data-photo="${esc(p.id)}" alt="${esc(p.name || "现场照片")}" loading="lazy">${caption ? `<figcaption>${esc(caption)}</figcaption>` : ""}</figure>`;
  }
  function composer() {
    return `<div class="composer ${!ui.record ? "home-composer" : ""}"><div class="attachment" ${ui.photo ? "" : "hidden"}>${ui.photo ? `<img src="${ui.photoUrl}" alt="待发送的照片"><span><strong>${esc(ui.photo.name)}</strong><small>已选好，还没发送</small></span><button class="icon-button" data-action="remove-photo" aria-label="移除待发送照片" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${icon("close")}</button>` : ""}</div>${ui.photoLoading ? '<p class="reading-photo"><span class="spinner"></span>正在读取照片…</p>' : ""}<p class="error" id="fileError" role="alert">${esc(ui.fileError)}</p><form id="messageForm"><label class="sr-only" for="messageInput">描述你看到的情况</label><textarea id="messageInput" rows="2" maxlength="4000" placeholder="例如：叶子发黄，最近越来越多…" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${esc(ui.draft)}</textarea><div class="composer-bottom"><button type="button" class="attach-button" data-action="photo" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${icon("camera")} ${ui.photo ? "换张照片" : "添加照片"}</button><button type="submit" id="sendButton" class="button primary" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${ui.busy ? '<span class="spinner"></span>正在整理示例' : "发给智麦 " + icon("arrow")}</button></div></form><p class="error" id="sendError" role="alert">${esc(ui.error)}</p>${ui.error ? '<button class="text-button" data-action="retry">重新发送</button>' : ""}<div class="composer-caption"><span>不必先填表，不知道的可以直接说</span><span>Shift + Enter 换行</span></div></div>`;
  }
  function home() {
    const last = S.records().find((r) => !r.archived);
    return `<section class="welcome"><div class="welcome-tag">${icon("leaf")} 专注冬小麦，陪你找到下一步</div><h1>小麦不对劲？<br>拍一张，一起看看。</h1><p>先查清原因，再核对用药。<br class="mobile-break">智麦一步步问，你照着说就好。</p></section><div class="home-workspace"><section class="start-card"><button class="photo-start" data-action="photo"><span class="camera-badge">${icon("camera")}</span><strong>拍照看病虫害</strong><span>拍清异常部位，能拍全株更好</span><b>选择或拍摄照片 ${icon("arrow")}</b></button><div class="or-label"><span></span>也可以直接说<span></span></div>${composer()}</section><aside class="home-aside"><button class="medicine-entry" data-action="medicine"><span class="entry-icon">${icon("book")}</span><span><strong>手里的药，能不能用？</strong><small>看登记号，核对作物和防治对象</small></span>${icon("chevron")}</button><section class="quick-questions"><h2>不知道怎么说？试试这些</h2>${["叶片发黄了", "发现了小虫子", "叶子上有白色粉状物"].map((t) => `<button data-action="quick" data-text="${t}">${icon("leaf")}<span>${t}</span>${icon("arrow")}</button>`).join("")}</section>${last ? `<section class="last-record"><span class="small-label">上次的问题，接着看看</span><h2>${esc(last.title)}</h2><p>${day(last.updatedAt)}${last.demo ? " · 示例过程" : ""}</p><div><a href="index.html?record=${encodeURIComponent(last.id)}">继续查看 ${icon("arrow")}</a><button data-action="open-followup" data-id="${esc(last.id)}">拍照复查</button></div></section>` : `<section class="simple-promise">${icon("history")}<div><strong>这次的问题，会帮你记着</strong><p>下次带照片回来，<br>就能对照之前的情况继续看。</p></div></section>`}</aside></div>`;
  }
  const actionButton = (action, text, ic, primary = false) =>
    `<button class="${primary ? "button primary" : "button secondary"}" data-action="${action}" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${ic ? icon(ic) : ""}${text}</button>`;
  function resultActions(m) {
    if (m.actions?.length === 1 && m.actions[0] === "summary")
      return `<div class="answer-actions">${actionButton("summary", "下载问题摘要", "download")}</div>`;
    if (m.type === "check")
      return `<div class="answer-actions">${actionButton("label", "拍清标签", "camera", true)}${actionButton("summary", "请农技人员帮看", "download")}</div>`;
    return `<div class="answer-actions">${actionButton("photo", "补拍一张照片", "camera", true)}${actionButton("medicine", "核对手里的药", "book")}</div>`;
  }
  function messageHTML(m, last) {
    const photos = ui.record?.photos || [];
    const p = photos.find((x) => x.id === m.photoId);
    if (m.role === "user")
      return `<article class="message user"><div class="user-bubble">${p ? photoHTML(p) : ""}${m.text ? `<p>${esc(m.text)}</p>` : ""}</div><span class="user-avatar">我</span></article>`;
    let content = "";
    if (m.type === "question")
      content = `<p class="question-text">${esc(m.text)}</p>${m.hint ? `<p class="message-hint">${esc(m.hint)}</p>` : ""}${last && m.choices ? `<div class="choices" aria-label="选择回答">${m.choices.map((t) => `<button data-action="answer" data-text="${esc(t)}" ${ui.busy || ui.photoLoading ? "disabled" : ""}>${esc(t)}</button>`).join("")}</div>` : ""}`;
    else if (["result", "check", "followup-result"].includes(m.type)) {
      const before = photos.find((p) => p.id === m.beforeId),
        after = photos.find((p) => p.id === m.afterId);
      content = `<section class="answer-card ${m.tone === "danger" ? "danger" : ""}"><span class="answer-source">${m.type === "check" ? "登记核对示例" : "示例回复 · 未识别实际图片"}</span><h2>${esc(m.heading)}</h2><p>${esc(m.summary)}</p>${m.checks?.length ? `<dl class="label-facts">${m.checks.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>` : ""}${m.now ? `<div class="next-step"><span>${icon("arrow")} 现在可以这样做</span><p>${esc(m.now)}</p></div>` : ""}${before && after && before.id !== after.id ? `<div class="photo-pair">${photoHTML(before, "上次记录 · " + day(before.date))}${photoHTML(after, "本次补充 · " + day(after.date))}</div><p class="message-hint">位置、光照不同会影响比较，照片不能单独证明药效。</p>` : ""}${m.medicine ? `<p class="medicine-note">${icon("book")}${esc(m.medicine)}</p>` : ""}${m.explanation ? `<details class="explanation"><summary>为什么这样说？</summary><p>${esc(m.explanation)}</p></details>` : ""}${last ? resultActions(m) : ""}</section>`;
    } else if (m.type === "legacy") {
      content = `<p>${esc(m.text)}</p><button class="text-button" data-action="old-detail">查看之前的现场记录 ${icon("chevron")}</button>${last ? `<div class="answer-actions">${actionButton("followup", "带新照片来复查", "camera", true)}${actionButton("medicine", "核对手里的药", "book")}</div>` : ""}`;
    } else
      content = `<p>${esc(m.text)}</p>${last ? `<div class="answer-actions">${actionButton("followup", "继续复查", "camera")}${actionButton("summary", "下载问题摘要", "download")}</div>` : ""}`;
    return `<article class="message assistant"><span class="assistant-avatar">${icon("wheat")}</span><div class="assistant-content"><span class="speaker">智麦 <i>·</i> ${ui.record.demo ? "交互演示" : "本地记录"}</span>${content}</div></article>`;
  }
  function conversation() {
    const t = ui.record,
      last = t.messages.filter((m) => m.role === "assistant").at(-1)?.id;
    return `<section class="thread-heading"><div><a class="back-link" href="history.html">${icon("back")} 我的记录</a><h1>${esc(t.title)}</h1><p>${day(t.createdAt)} · ${t.archived ? "这次跟踪已结束" : "这次的问题，会接着记"}${t.demo ? " · 演示过程" : ""}</p></div><button class="icon-button" data-action="more" aria-label="这条记录的更多操作">${icon("more")}</button></section><section class="conversation" aria-label="问题与回答"><div class="messages" role="log" aria-live="polite">${t.messages.map((m) => messageHTML(m, m.id === last)).join("")}${ui.busy ? `<div class="thinking"><span class="spinner"></span>正在整理演示回复…</div>` : ""}</div>${t.followupDate ? `<div class="followup-date">${icon("clock")}你计划在 ${day(t.followupDate)} 再来看看 <small>日期已保存，暂不推送通知</small></div>` : ""}${t.archived ? `<div class="closed-record">这次跟踪已结束。<button class="text-button" data-action="reopen">继续跟踪</button></div>` : `<div class="followup-tools"><button data-action="action">${icon("check")}记下我做了什么</button><button data-action="schedule">${icon("clock")}约个时间复查</button></div>${composer()}`}<div id="threadEnd"></div></section>`;
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
    return `<section class="records-heading"><div><span class="small-label">之前的问题，都在这里</span><h1>我的记录</h1><p>带着新照片回来，继续看看有没有变化。</p></div><a class="button primary" href="index.html">${icon("plus")}问个新问题</a></section><p class="storage-note">${icon("history")}记录和照片仅保存在当前设备，请勿清理浏览器数据。</p>${all.length > 6 ? `<label class="record-search">${icon("search")}<input id="recordSearch" placeholder="找之前的问题" value="${esc(ui.search)}" aria-label="搜索记录"></label>` : ""}<div class="record-list">${rs.map((t) => `<article class="record-row"><a class="record-main" href="index.html?record=${encodeURIComponent(t.id)}"><div class="record-thumbnail">${t.photos[0] ? `<img data-photo="${esc(t.photos[0].id)}" data-record="${esc(t.id)}" alt="此前的照片" loading="lazy">` : icon(t.kind === "medicine" ? "book" : "leaf")}</div><div><span class="record-date">${day(t.updatedAt)}${t.demo ? " · 演示过程" : ""}</span><h2>${esc(t.title)}</h2><p>${esc(recordState(t))}${t.followupDate ? " · " + day(t.followupDate) : ""}</p></div></a><div class="record-row-actions">${!t.archived ? `<button class="button secondary" data-action="open-followup" data-id="${esc(t.id)}">${icon("camera")}来复查</button>` : ""}<button class="icon-button" data-action="record-more" data-id="${esc(t.id)}" aria-label="管理${esc(t.title)}">${icon("more")}</button></div></article>`).join("") || `<section class="empty-records"><span>${icon("leaf")}</span><h2>${all.length ? "没找到这条记录" : "还没有记录，先从一个问题开始"}</h2><p>拍照或说说情况，智麦会帮你留住这次的观察。</p><a class="button primary" href="index.html">去问智麦 ${icon("arrow")}</a></section>`}</div>`;
  }
  function render(options = {}) {
    root.innerHTML = `${S.readError ? `<p class="storage-error" role="alert">${esc(S.readError)}</p>` : ""}${requested && !ui.record && !isHistory ? `<section class="empty-records"><h1>这条记录不在当前设备中</h1><p>可以回到我的记录重新选择。旧版服务端记录暂未在这个原型中加载。</p><a class="button primary" href="history.html">查看我的记录</a></section>` : isHistory ? history() : ui.record ? conversation() : home()}`;
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
    ui.busy = true;
    ui.error = "";
    render({ scroll: Boolean(ui.record) });
    let savedPhoto = null;
    try {
      if (ui.photo) savedPhoto = await S.putPhoto(ui.photo);
      const next = await A.respond(ui.record, {
        text,
        photo: savedPhoto,
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
    if (saveTransition(next) && labelPhoto)
      document.getElementById("photoInput").click();
  }
  function startFollowup(record = ui.record, pick = false) {
    if (!record) return;
    if (isHistory) {
      location.href = `index.html?record=${encodeURIComponent(record.id)}&followup=1`;
      return;
    }
    if (saveTransition(A.startFollowup(record)) && pick)
      document.getElementById("photoInput").click();
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
      `来源：${record.demo ? "交互演示，非真实诊断" : "此前保存的现场资料"}`,
      `问题：${record.facts?.description || record.title}`,
      `分布：${record.facts?.distribution || "未确认"}；生育期：${record.facts?.stage || "未确认"}`,
      record.facts?.registration
        ? `待核对登记号：${record.facts.registration}；防治对象：${record.facts.target || "未确认"}`
        : "",
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
      "这是可操作的前端演示",
      `<p>你可以拍照、一步步回答、核对演示登记号，再保存处理和复查记录。</p><p>当前没有调用真实图像识别、标签 OCR、登记查询或后台提醒。示例回复不用于实际病虫害诊断或施药。</p><details class="demo-examples"><summary>体验药品核对示例</summary><p>以下都是虚构编号，不对应真实产品。</p><button class="button secondary" data-action="example-drug" data-number="DEMO-WHEAT-001">看一个字段相符的例子</button><button class="button secondary" data-action="example-drug" data-number="DEMO-MISMATCH-001">看一个不匹配的例子</button></details><p class="dialog-note">记录和照片仅在本机保存。更换设备或清理浏览器数据可能导致无法读取；建议下载重要记录的文字摘要。</p>`,
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
    if (action === "retry") send();
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
        `<div class="help-step"><b>1</b><div><h3>拍张照片，或说说异常</h3><p>不用建地块档案。看不清的地方，后面再补。</p></div></div><div class="help-step"><b>2</b><div><h3>跟着问题，一次答一句</h3><p>不知道就选“不清楚”。手里有药，也可以在对话中核对。</p></div></div><div class="help-step"><b>3</b><div><h3>回来复查，接着看变化</h3><p>从“我的记录”找到上次的问题，带着新照片回来。</p></div></div><button class="text-button" data-action="scope">查看演示范围与示例 ${icon("chevron")}</button>`,
      );
    if (action === "example-drug") {
      U.close();
      if (isHistory) {
        location.href = `index.html?example=${encodeURIComponent(b.dataset.number)}`;
        return;
      }
      const t = A.startMedicine(null);
      if (saveTransition(t)) send(b.dataset.number);
    }
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
  if (!isHistory && !requested && params.get("example")) {
    const t = A.startMedicine(null);
    if (saveTransition(t)) send(params.get("example"));
  }
})();
