/* Safe rendering and the image/chat state machine, usable with or without a backend. */
(() => {
  "use strict";
  const Z = window.ZM,
    { icon, esc, badge } = Z;
  function inline(text) {
    return esc(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
      );
  }
  function markdown(text) {
    const lines = String(text || "")
      .replace(/\r\n/g, "\n")
      .split("\n");
    let html = "",
      paragraph = [],
      list = "",
      code = null;
    const flushP = () => {
      if (paragraph.length) {
        html += `<p>${paragraph.map(inline).join("<br>")}</p>`;
        paragraph = [];
      }
    };
    const flushL = () => {
      if (list) {
        html += `</${list}>`;
        list = "";
      }
    };
    for (const line of lines) {
      if (/^\s*```/.test(line)) {
        flushP();
        flushL();
        if (code !== null) {
          html += `<pre><code>${esc(code.join("\n"))}</code></pre>`;
          code = null;
        } else code = [];
        continue;
      }
      if (code !== null) {
        code.push(line);
        continue;
      }
      if (!line.trim()) {
        flushP();
        flushL();
        continue;
      }
      const m = line.match(/^\s*(?:([-*])\s+|(\d+)[.)、]\s+)(.*)/);
      if (m) {
        flushP();
        const kind = m[1] ? "ul" : "ol";
        if (list !== kind) {
          flushL();
          html += `<${kind}>`;
          list = kind;
        }
        html += `<li>${inline(m[3])}</li>`;
        continue;
      }
      flushL();
      if (/^#{1,6}\s/.test(line)) {
        flushP();
        html += `<p><strong>${inline(line.replace(/^#{1,6}\s+/, ""))}</strong></p>`;
      } else paragraph.push(line);
    }
    flushP();
    flushL();
    if (code !== null)
      html += `<pre><code>${esc(code.join("\n"))}</code></pre>`;
    return html;
  }
  Z.markdown = markdown;
  if (document.body.dataset.page !== "diagnosis") return;
  const API = window.ZhimaiAPI,
    root = Z.root,
    params = new URLSearchParams(location.search),
    demo = Z.mode === "demo";
  const d = {
    file: null,
    preview: "",
    imageStatus: "empty",
    vision: "",
    imagePath: null,
    consumed: false,
    imageError: "",
    imageVersion: 0,
    caseId: params.get("caseId") || null,
    recheck: Boolean(params.get("caseId")),
    conversationId: params.get("conversationId") || null,
    messages: [],
    sending: false,
    restoring: false,
    restoreError: "",
    requestController: null,
    uploadController: null,
    selectedField: params.get("fieldId") || Z.state.fields[0]?.id || "",
    caseLabel: "",
  };
  const toolNames = {
    get_weather: "天气查询",
    get_soil: "土壤墒情",
    search_knowledge: "知识检索",
  };
  const time = () =>
    new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    }).format(new Date());
  const suggestions = [
    "叶片局部发黄，先观察什么？",
    "怎样拍照，方便下次复查？",
    "查天气前，需要哪些信息？",
    "如何记录近期水肥操作？",
  ];
  function layout() {
    root.innerHTML = `<div class="diagnosis-intro"><div><span class="eyebrow">OBSERVE · UNDERSTAND · FOLLOW UP</span><h1>田间的疑问，和智麦一起梳理。</h1><p class="muted" style="font-size:12px;margin-top:7px">先看见，再判断。图片观察与进一步推断，清楚分开。</p></div><a class="btn" href="history.html">${icon("history")} 回看诊断历史</a></div><div class="notice ${demo ? "amber" : ""} mb">${icon("book")}<span>${demo ? "当前为交互演示：图片不会发送给模型，回答为固定场景示例，不用于实际农业决策。" : "已选择后端连接模式。识别与回复以实际接口结果为准，未返回的数据不会补造。"}</span>${!demo ? '<button class="text-link" data-action="settings">连接设置</button>' : ""}</div><div id="caseBanner"></div><div class="diagnosis-layout"><aside class="diagnosis-side"><section class="panel"><div class="panel-head"><div><h2>先留下一张田间照片</h2><p>也可以不上传图片，直接提问</p></div>${icon("image")}</div><div class="upload-body"><label class="sr-only" for="imageInput">选择小麦图片</label><input id="imageInput" type="file" accept="image/jpeg,image/png,image/webp" hidden><button class="upload-zone" id="uploadZone"><span class="upload-symbol">${icon("upload")}</span><strong>点击选择，或拖入一张图片</strong><small>JPG / PNG / WEBP · 最大 4 MB<br>建议同时记录固定采样点与拍摄日期</small></button><div id="photoPreview" hidden><div class="preview-wrap"><img id="previewImg" alt="本次选中的田间照片"><button class="icon-btn preview-remove" id="removeImage" aria-label="移除当前图片">${icon("close")}</button></div><p class="preview-filename" id="previewFilename"></p><div class="preview-actions"><span class="badge gray">本次图片</span><button class="text-link" id="changeImage">${icon("refresh")} 重新选择</button></div></div><p class="vision-disclaimer">选择图片只${demo ? "准备演示" : "进行识别"}，不会自动发送聊天。移除图片会保留当前对话。</p></div></section><section class="panel" id="visionPanel" hidden><div class="panel-head"><div><h2>图片观察</h2><p>${demo ? "固定演示描述，非图像识别结果" : "视觉模型实际返回的描述"}</p></div>${badge(demo ? "演示" : "图像观察", "gray")}</div><div class="panel-body"><div class="vision-status" id="visionStatus"></div><div class="vision-result" id="visionResult"></div><div id="visionRetry" hidden><button class="btn small" id="retryImage">${icon("refresh")} 重试识别</button></div><p class="vision-disclaimer">可见特征不等于确定病因。具体判断仍需结合生育期、分布与管理记录。</p></div></section><section class="panel tips-panel"><div class="panel-head"><h2>让下次比较更有依据</h2>${icon("leaf")}</div><ul class="tips-list"><li>${icon("pin")}尽量固定采样位置，同时保留全景与近景。</li><li>${icon("sun")}使用相近光照、角度与距离，减少拍摄差异。</li><li>${icon("calendar")}记录近期实际操作，便于解释前后变化。</li></ul></section></aside><section class="panel chat-card"><div class="chat-header"><span class="agent-avatar">${icon("wheat")}</span><div><h2>智麦 · 田间观察助手</h2><small>${demo ? "演示对话 · 不调用真实模型" : "连接后端 · 回复来源可核对"}</small></div>${badge(demo ? "演示模式" : "实际接口", demo ? "amber" : "green")}<button class="icon-btn" id="newConversation" aria-label="开始新会话" title="开始新会话">${icon("plus")}</button></div><div class="chat-messages" id="chatMessages" role="log" aria-label="与智麦的对话" aria-live="polite"></div><div class="chat-composer"><div class="attachment-context" id="attachmentContext" hidden></div><div id="restoreNotice"></div><div class="composer-field"><label class="sr-only" for="chatInput">输入你的田间问题</label><textarea id="chatInput" rows="2" maxlength="12000" placeholder="说说你观察到的情况，或直接提出问题…"></textarea><button class="send-btn" id="sendBtn" aria-label="发送消息">${icon("send")}</button></div><div class="composer-hint"><span id="composerHint">${demo ? "示例回答仅用于体验，不代表真实诊断" : "图像与模型回答仅作辅助，请结合现场证据"}</span><span>Enter 发送 · Shift + Enter 换行</span></div></div></section></div>`;
    document.getElementById("uploadZone").onclick = () =>
      document.getElementById("imageInput").click();
    document.getElementById("changeImage").onclick = () =>
      document.getElementById("imageInput").click();
    document.getElementById("removeImage").onclick = clearPhoto;
    document.getElementById("retryImage").onclick = () =>
      d.file && choosePhoto(d.file);
    const zone = document.getElementById("uploadZone");
    zone.ondragover = (e) => {
      e.preventDefault();
      if (!d.sending) zone.classList.add("dragging");
    };
    zone.ondragleave = () => zone.classList.remove("dragging");
    zone.ondrop = (e) => {
      e.preventDefault();
      zone.classList.remove("dragging");
      if (!d.sending && e.dataTransfer.files[0])
        choosePhoto(e.dataTransfer.files[0]);
    };
    document.getElementById("imageInput").onchange = (e) => {
      if (e.target.files[0]) choosePhoto(e.target.files[0]);
    };
    document.getElementById("sendBtn").onclick = () =>
      d.sending ? d.requestController?.abort() : send();
    document.getElementById("chatInput").onkeydown = (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        if (!d.sending) send();
      }
    };
    document.getElementById("newConversation").onclick = newConversation;
    document.getElementById("chatMessages").addEventListener("click", (e) => {
      const s = e.target.closest("[data-suggestion]");
      if (s) {
        document.getElementById("chatInput").value = s.dataset.suggestion;
        document.getElementById("chatInput").focus();
      }
      const r = e.target.closest("[data-retry-message]");
      if (r && !d.sending) {
        const m = d.messages.find((m) => m.id === r.dataset.retryMessage);
        if (m) send(m.request, m);
      }
      const save = e.target.closest("[data-save-observation]");
      if (save) {
        const m = d.messages.find((m) => m.id === save.dataset.saveObservation);
        if (m)
          Z.newRecord(d.selectedField, "观察", {
            title: demo ? "演示对话参考（未执行真实诊断）" : "诊断对话参考",
            note: `${demo ? "以下为固定演示回答，非真实诊断。" : "以下为模型生成的参考内容，需结合现场证据确认。"}\n\n${m.content}`,
          });
      }
      const task = e.target.closest("[data-followup-task]");
      if (task)
        Z.newTask(
          d.selectedField,
          "补充下一轮现场观察",
          "结合对话中仍待确认的信息补拍或补充记录。",
        );
    });
    renderMessages();
    renderPhoto();
    renderBanner();
    sync();
  }
  function renderBanner() {
    const el = document.getElementById("caseBanner");
    el.innerHTML = d.recheck
      ? `<div class="recheck-banner">${icon("refresh")}<span><strong>正在继续跟踪${d.caseLabel ? "：" + esc(d.caseLabel) : "此前案例"}</strong><small>${demo ? "演示复查会保留原案例，并追加对话。" : "新图片识别与后续聊天将沿用当前案例上下文。"}</small></span><a href="history.html">查看历史</a></div>`
      : "";
  }
  function welcome() {
    return `<div class="chat-welcome"><span class="agent-avatar">${icon("wheat")}</span><h3>今天，麦田有什么新变化？</h3><p>上传一张照片，或描述你观察到的情况。<br>从已有证据出发，一起找到值得关注的下一步。</p><div class="suggestion-grid">${suggestions.map((s, i) => `<button class="suggestion" data-suggestion="${esc(s)}">${icon(["leaf", "image", "cloud", "calendar"][i])}<span>${s}</span></button>`).join("")}</div></div>`;
  }
  function toolHTML(m) {
    return (m.tools || [])
      .map(
        (t) =>
          `<details class="tool-trace"><summary>${esc(toolNames[t.tool] || t.tool)} · ${esc(t.source || "来源未提供")}</summary><pre>${esc(typeof t.result === "string" ? t.result : JSON.stringify(t.result, null, 2))}</pre></details>`,
      )
      .join("");
  }
  function messageHTML(m) {
    const isUser = m.role === "user";
    return `<article class="message-item ${isUser ? "user" : "agent"}" id="msg-${esc(m.id)}"><span class="message-avatar">${isUser ? "我" : icon("wheat")}</span><div class="message-content"><div class="message-meta"><span>${isUser ? "我" : demo ? "智麦 · 演示" : "智麦"}</span><time>${esc(m.when || "")}</time></div>${toolHTML(m)}<div class="message-bubble ${m.processing && !m.content ? "processing" : ""}">${m.content ? (isUser ? esc(m.content) : markdown(m.content)) : `<span class="spinner"></span>${esc(m.status || "正在请求回复…")}`}</div>${m.error ? `<div class="message-error" role="alert">${esc(m.error)}${m.request && !m.stopped ? `<button class="btn small" data-retry-message="${esc(m.id)}">${icon("refresh")} 重试此问题</button>` : ""}</div>` : ""}${!isUser && !m.processing && !m.error ? `<div class="message-tools">${icon("book")}${demo ? "固定场景演示 · 非真实诊断" : "依据当前对话生成 · 请核对现场信息"}</div><div class="message-followups"><button class="text-link" data-save-observation="${esc(m.id)}">${icon("history")} 加入地块记录</button><button class="text-link" data-followup-task="${esc(m.id)}">${icon("calendar")} 安排后续复查</button></div>` : ""}</div></article>`;
  }
  function renderMessages() {
    const el = document.getElementById("chatMessages");
    el.innerHTML = d.messages.length
      ? d.messages.map(messageHTML).join("")
      : welcome();
    el.scrollTop = el.scrollHeight;
  }
  function updateMessage(m) {
    const el = document.getElementById(`msg-${m.id}`);
    if (el) el.outerHTML = messageHTML(m);
    else renderMessages();
    const box = document.getElementById("chatMessages");
    box.scrollTop = box.scrollHeight;
  }
  function renderPhoto() {
    const has = Boolean(d.file);
    document.getElementById("uploadZone").hidden = has;
    document.getElementById("photoPreview").hidden = !has;
    document.getElementById("visionPanel").hidden = !has;
    if (has) {
      document.getElementById("previewImg").src = d.preview;
      document.getElementById("previewFilename").textContent =
        `${d.file.name} · ${(d.file.size / 1024).toFixed(0)} KB`;
      const status = document.getElementById("visionStatus");
      status.className = `vision-status ${d.imageStatus === "failed" ? "error" : ""}`;
      status.innerHTML =
        d.imageStatus === "recognizing"
          ? `<span class="spinner"></span>${demo ? "正在准备演示图片…" : "正在请求图片识别…"}`
          : d.imageStatus === "failed"
            ? `${icon("alert")} 识别未完成`
            : `${icon("check")}${d.consumed ? "本次图片上下文已用于上一轮对话" : demo ? "演示图片已就绪" : "图片识别完成，等待发送问题"}`;
      document.getElementById("visionResult").innerHTML =
        d.imageStatus === "failed"
          ? esc(d.imageError)
          : d.imageStatus === "ready"
            ? markdown(d.vision)
            : '<p class="muted">完成后将在这里显示本次结果；不会使用上一张图片的描述。</p>';
      document.getElementById("visionRetry").hidden =
        d.imageStatus !== "failed";
    }
    const context = document.getElementById("attachmentContext");
    context.hidden = !(d.imageStatus === "ready" && !d.consumed);
    context.innerHTML = `${icon("image")}本轮将携带当前图片${demo ? "演示上下文" : "识别结果"}`;
    sync();
  }
  function sync() {
    const blocked = d.sending || d.restoring;
    document.getElementById("chatInput").disabled =
      blocked || d.imageStatus === "recognizing";
    document.getElementById("sendBtn").disabled =
      d.restoring || d.imageStatus === "recognizing" || Boolean(d.restoreError);
    document
      .getElementById("sendBtn")
      .setAttribute("aria-label", d.sending ? "停止接收回复" : "发送消息");
    document.getElementById("sendBtn").innerHTML = icon(
      d.sending ? "close" : "send",
    );
    [
      "uploadZone",
      "changeImage",
      "removeImage",
      "retryImage",
      "newConversation",
    ].forEach((id) => {
      document.getElementById(id).disabled = blocked;
    });
    document.getElementById("imageInput").disabled = blocked;
    const notice = document.getElementById("restoreNotice");
    notice.innerHTML = d.restoring
      ? '<div class="notice mb"><span class="spinner"></span>正在恢复已有记录…</div>'
      : d.restoreError
        ? `<div class="notice error mb">${icon("alert")}<span>恢复失败：${esc(d.restoreError)}<br><button class="text-link" id="retryRestore">重新恢复</button> · <button class="text-link" id="startFresh">开始新会话</button></span></div>`
        : "";
    const r = document.getElementById("retryRestore");
    if (r) r.onclick = restore;
    const f = document.getElementById("startFresh");
    if (f) f.onclick = resetConversation;
  }
  async function choosePhoto(file) {
    if (d.sending || d.restoring) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      Z.toast("请选择 JPG、PNG 或 WEBP 图片。", "error");
      return;
    }
    if (file.size > 4 * 1024 * 1024 || !file.size) {
      Z.toast(
        file.size ? "图片超过 4 MB，请选择较小的图片。" : "图片内容为空。",
        "error",
      );
      return;
    }
    d.uploadController?.abort();
    const version = ++d.imageVersion;
    if (d.preview) URL.revokeObjectURL(d.preview);
    d.file = file;
    d.preview = URL.createObjectURL(file);
    d.imageStatus = "recognizing";
    d.vision = "";
    d.imagePath = null;
    d.consumed = false;
    d.imageError = "";
    if (!d.recheck) d.caseId = null;
    d.uploadController = new AbortController();
    renderPhoto();
    try {
      let result;
      if (demo) {
        await delay(550, d.uploadController.signal);
        result = {
          result:
            "**交互演示说明**\n\n图片已接收，但当前模式没有调用视觉模型，也未分析这张照片。\n\n正式观察时，可以记录：\n- 叶片颜色及可见斑点。\n- 异常在田间的分布。\n- 生育期与近期实际管理操作。\n\n输入问题后，可继续体验示例对话。",
        };
      } else
        result = await API.uploadImage(
          file,
          undefined,
          d.recheck ? d.caseId : undefined,
          d.uploadController.signal,
        );
      if (version !== d.imageVersion) return;
      if (typeof result.result !== "string" || !result.result.trim())
        throw new Error("图片接口未返回有效识别描述。");
      d.vision = result.result;
      d.imagePath = result.image_path || null;
      if (!d.recheck && !demo) d.caseId = result.case_id ?? null;
      d.imageStatus = "ready";
    } catch (err) {
      if (version !== d.imageVersion) return;
      if (err.name === "AbortError") return;
      d.imageStatus = "failed";
      d.vision = "";
      d.imagePath = null;
      d.imageError = err.message || "图片识别失败，请检查连接后重试。";
    } finally {
      if (version === d.imageVersion) renderPhoto();
    }
  }
  function clearPhoto() {
    d.uploadController?.abort();
    d.imageVersion++;
    if (d.preview) URL.revokeObjectURL(d.preview);
    Object.assign(d, {
      file: null,
      preview: "",
      imageStatus: "empty",
      vision: "",
      imagePath: null,
      consumed: false,
      imageError: "",
    });
    document.getElementById("imageInput").value = "";
    renderPhoto();
  }
  function delay(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal.removeEventListener("abort", abort);
        resolve();
      }, ms);
      signal.addEventListener("abort", abort, { once: true });
    });
  }
  const sourceOf = (result) => {
    try {
      const r = typeof result === "string" ? JSON.parse(result) : result;
      return r.source || "来源未提供";
    } catch {
      return "来源未提供";
    }
  };
  async function demoAnswer(req, m, signal) {
    const text = req.message;
    let answer;
    if (/天气|降雨|浇水/.test(text)) {
      m.status = "正在展示天气工具调用示例…";
      updateMessage(m);
      await delay(500, signal);
      m.tools.push({
        tool: "get_weather",
        source: "模拟",
        result: JSON.stringify(
          {
            location: "郑州（示例）",
            weather: "晴间多云",
            temperature: "12~22℃",
            source: "模拟",
            note: "固定演示值，未请求真实天气服务",
          },
          null,
          2,
        ),
      });
      answer =
        "**以下为天气场景演示，非实时天气。**\n\n示例天气工具返回了“郑州、晴间多云、12～22℃”，来源明确标记为**模拟**。这些数据不能用于决定实际灌溉或其他农事。\n\n要进一步讨论田间管理，还需要：\n1. 确认地块位置和当前生育期。\n2. 补充当地实际降雨与田间墒情。\n3. 说明近期已经进行的管理操作。\n\n你可以把缺失的信息记成一项跟踪任务。";
    } else if (/拍|照片|对比|复查/.test(text)) {
      answer =
        "**以下为固定场景演示。**\n\n为了让前后观察更可比，建议：\n1. 固定采样位置，尽量保持相近角度和距离。\n2. 同时拍田间全景与叶片近景。\n3. 记录日期、生育期和期间实际发生的农事操作。\n\n如果拍摄条件不同，颜色差异可能来自光照，不能直接解释为长势改变。\n\n下一步可以进入**生长对比**，并排查看两次观察，再保存自己的复查记录。";
    } else if (/知识|依据|资料/.test(text)) {
      m.status = "正在展示知识检索状态…";
      updateMessage(m);
      await delay(400, signal);
      m.tools.push({
        tool: "search_knowledge",
        source: "模拟",
        result: "知识检索尚未连接真实资料，演示不提供虚构引用。",
      });
      answer =
        "**当前未检索真实知识库。**\n\n本演示不生成资料标题、出处或虚构引用。连接实际后端后，工具返回的结果会保留其来源；没有检索依据时，应明确说明。\n\n判断资料是否适用，还需要核对作物、地区、生育期与具体条件。";
    } else if (/水肥|施肥|操作|记录/.test(text)) {
      answer =
        "**以下为农事记录场景演示。**\n\n建议先如实记录：\n- 实际操作日期与所属地块。\n- 做了什么操作，已知的投入品信息。\n- 操作前现场情况，以及后续需要观察的变化。\n\n不清楚的数据可以标记为待补充，不需要猜测。涉及施肥剂量，应结合可靠依据与适用条件进一步确认。\n\n你可以在地块档案中添加一条**农事记录**，再安排复查任务。";
    } else {
      answer =
        "**以下为固定诊断场景演示，未分析你的图片或调用模型。**\n\n以“叶片局部发黄”为例，现有信息通常不足以直接确定原因。值得先补充：\n1. 当前处于哪个生育期？\n2. 异常是局部出现，还是全田普遍发生？\n3. 最近是否有施肥、灌溉或明显天气变化？\n\n可先补拍全景并记录近期管理情况，保留不确定性，再决定下一步检查。\n\n你可以在**地块档案**中留下观察，并为后续补拍建立任务。";
    }
    await delay(450, signal);
    m.status = "正在展示演示回答…";
    for (let i = 0; i < answer.length; i += 24) {
      await delay(22, signal);
      m.content += answer.slice(i, i + 24);
      updateMessage(m);
    }
    return {
      done: true,
      conversation_id: d.conversationId || `demo-${Z.uid()}`,
      case_id: d.caseId,
    };
  }
  async function send(retryRequest, retryMessage) {
    if (
      d.sending ||
      d.restoring ||
      d.imageStatus === "recognizing" ||
      d.restoreError
    )
      return;
    const input = document.getElementById("chatInput");
    const text = retryRequest?.message || input.value.trim();
    if (!text) {
      input.focus();
      return;
    }
    if (d.imageStatus === "failed" && !retryRequest) {
      Z.toast(
        "当前图片识别失败。请重试识别，或移除图片后发送纯文本。",
        "error",
      );
      return;
    }
    const req = retryRequest
      ? {
          ...retryRequest,
          conversation_id: d.conversationId || retryRequest.conversation_id,
        }
      : {
          message: text,
          conversation_id: d.conversationId,
          vision_result:
            d.imageStatus === "ready" && !d.consumed ? d.vision : null,
          case_id: d.caseId,
          image_path:
            d.imageStatus === "ready" && !d.consumed ? d.imagePath : null,
        };
    let m = retryMessage;
    if (m) {
      m.content = "";
      m.error = "";
      m.tools = [];
      m.processing = true;
      m.status = "正在重新请求回复…";
      m.stopped = false;
    } else {
      d.messages.push({
        id: Z.uid(),
        role: "user",
        content: text,
        when: time(),
      });
      m = {
        id: Z.uid(),
        role: "assistant",
        content: "",
        when: time(),
        tools: [],
        processing: true,
        status: demo ? "正在准备演示回答…" : "正在请求回复…",
        request: req,
      };
      d.messages.push(m);
      input.value = "";
    }
    d.sending = true;
    d.requestController = new AbortController();
    renderMessages();
    sync();
    try {
      const meta = demo
        ? await demoAnswer(req, m, d.requestController.signal)
        : await API.sendChatStream(
            req,
            (delta) => {
              m.content += delta;
              updateMessage(m);
            },
            (call) => {
              m.status = `正在调用${toolNames[call.tool] || call.tool}…`;
              updateMessage(m);
            },
            (result) => {
              m.tools.push({ ...result, source: sourceOf(result.result) });
              m.status = "已收到工具结果，正在等待回答…";
              updateMessage(m);
            },
            d.requestController.signal,
          );
      if (!meta.done) throw new Error("未收到回复完成确认。");
      d.conversationId = meta.conversation_id || d.conversationId;
      d.caseId = meta.case_id ?? d.caseId;
      m.processing = false;
      m.done = true;
      if (req.vision_result) d.consumed = true;
      if (demo) await persistDemo(req, m);
      else {
        try {
          localStorage.setItem(
            "zhimai.liveConversation",
            String(d.conversationId),
          );
        } catch {
          Z.toast("当前浏览器无法保存会话恢复信息。", "error");
        }
      }
    } catch (err) {
      m.processing = false;
      if (err.conversation_id) {
        d.conversationId = err.conversation_id;
        if (!demo) {
          try {
            localStorage.setItem(
              "zhimai.liveConversation",
              String(d.conversationId),
            );
          } catch {}
        }
      }
      if (err.case_id) d.caseId = err.case_id;
      m.stopped = err.name === "AbortError";
      m.error = m.stopped
        ? "已停止接收回复。连接后端时，服务端处理可能仍在继续。"
        : `${m.content ? "已保留收到的部分内容。" : ""}${err.message || "请求失败，请检查连接后重试。"}`;
      if (!m.content)
        m.content = m.stopped ? "接收已停止。" : "本次未获得完整回复。";
    } finally {
      d.sending = false;
      d.requestController = null;
      updateMessage(m);
      renderPhoto();
      sync();
      input.focus();
    }
  }
  async function persistDemo(req, m) {
    const conversationId = d.conversationId;
    let nextCaseId = d.caseId;
    let photo = "";
    if (req.vision_result && d.file) {
      photo = await new Promise((resolve) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = () => resolve("");
        r.readAsDataURL(d.file);
      });
    }
    const saved = Z.commit((s) => {
      const chat = {
        id: conversationId,
        messages: d.messages
          .filter((m) => !m.processing && !m.error)
          .map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            when: m.when,
            tools: m.tools || [],
          })),
      };
      const i = s.chats.findIndex((c) => c.id === conversationId);
      if (i < 0) s.chats.push(chat);
      else s.chats[i] = chat;
      if (req.vision_result && !nextCaseId) {
        nextCaseId = `demo-${Z.uid()}`;
        s.cases.push({
          id: nextCaseId,
          image: photo,
          summary: "本地图片的交互演示记录，未执行真实识别。",
          recognition: d.vision,
          diagnosis: m.content,
          advice: "",
          status: "进行中",
          create_time: `${Z.today()} ${time()}`,
          conversation_id: conversationId,
          recheck_count: 0,
          demo: true,
        });
      } else if (nextCaseId) {
        const c = s.cases.find((c) => c.id === nextCaseId);
        if (c) {
          c.conversation_id = conversationId;
          if (req.vision_result) {
            c.recheck_count = (c.recheck_count || 0) + 1;
            c.last_recheck_time = `${Z.today()} ${time()}`;
          }
        } else {
          // Seed cases also need a durable association after a follow-up.
          s.caseLinks ??= {};
          const link = s.caseLinks[nextCaseId] || {};
          s.caseLinks[nextCaseId] = {
            ...link,
            conversation_id: conversationId,
          };
          if (req.vision_result) {
            s.caseLinks[nextCaseId].recheck_count =
              (link.recheck_count ?? (nextCaseId === "demo-east" ? 1 : 0)) + 1;
            s.caseLinks[nextCaseId].last_recheck_time =
              `${Z.today()} ${time()}`;
          }
        }
        if (req.vision_result && s.caseStatuses?.[nextCaseId] === "已完成")
          s.caseStatuses[nextCaseId] = "进行中";
      }
    });
    if (saved) {
      d.caseId = nextCaseId;
      try {
        localStorage.setItem("zhimai.demoConversation", conversationId);
      } catch {}
    }
  }
  function resetConversation() {
    d.restoreError = "";
    d.restoring = false;
    d.messages = [];
    d.conversationId = null;
    d.caseId = null;
    d.recheck = false;
    d.caseLabel = "";
    clearPhoto();
    try {
      localStorage.removeItem(
        demo ? "zhimai.demoConversation" : "zhimai.liveConversation",
      );
    } catch {}
    history.replaceState(null, "", "diagnosis.html");
    renderBanner();
    renderMessages();
    sync();
    document.getElementById("chatInput").value = "";
    Z.toast("已开始新会话，既有历史记录已保留");
  }
  function newConversation() {
    if (d.sending) return;
    if (!d.messages.length && !d.file && !d.recheck) {
      resetConversation();
      return;
    }
    Z.modal(
      "开始一次新的观察对话？",
      '<p class="form-intro">当前图片和对话将从工作区清除，已保存的历史记录会保留。</p>',
      () => {
        Z.closeModal();
        resetConversation();
      },
      { submit: "开始新会话" },
    );
  }
  async function restore() {
    d.restoring = true;
    d.restoreError = "";
    sync();
    try {
      if (demo) {
        if (d.caseId) {
          const c = Z.demoCases().find(
            (c) => String(c.id) === String(d.caseId),
          );
          if (!c) throw new Error("没有找到这条演示案例。");
          d.caseLabel = c.fieldId ? Z.field(c.fieldId)?.name : "本地演示案例";
          d.conversationId = c.conversation_id || d.conversationId;
          if (!d.conversationId)
            d.messages = [
              {
                id: Z.uid(),
                role: "assistant",
                content:
                  c.diagnosis || "这条示例案例尚未形成诊断，可继续补充信息。",
                when: "历史记录",
                tools: [],
              },
            ];
        }
        if (d.conversationId) {
          const c = Z.state.chats.find((c) => c.id === d.conversationId);
          if (!c) throw new Error("这段演示对话未保存在当前浏览器。");
          d.messages = c.messages.map((m) => ({ ...m }));
        }
      } else {
        if (d.caseId) {
          if (!/^\d+$/.test(d.caseId))
            throw new Error(
              "当前案例编号不属于实际后端，请切换演示模式或从诊断历史重新进入。",
            );
          const c = await API.getCaseDetail(d.caseId);
          d.caseLabel = `案例 #${c.id}`;
          d.conversationId = c.conversation_id || null;
        }
        if (d.conversationId) {
          if (!/^\d+$/.test(String(d.conversationId)))
            throw new Error("会话编号不正确。");
          const messages = await API.getConversationMessages(d.conversationId);
          if (!Array.isArray(messages))
            throw new Error("聊天历史返回格式不正确。");
          d.messages = messages.map((m) => ({
            id: Z.uid(),
            role: m.role,
            content: m.content || "",
            when: m.created_at || "",
            tools: [],
          }));
        }
      }
    } catch (err) {
      d.restoreError = err.message || "历史恢复失败。";
    } finally {
      d.restoring = false;
      renderBanner();
      renderMessages();
      sync();
    }
  }
  layout();
  if (!d.conversationId && !d.caseId)
    d.conversationId =
      Z.readSetting(
        demo ? "zhimai.demoConversation" : "zhimai.liveConversation",
        "",
      ) || null;
  if (d.conversationId || d.caseId) restore();
  window.addEventListener("beforeunload", () => {
    d.uploadController?.abort();
    d.requestController?.abort();
    if (d.preview) URL.revokeObjectURL(d.preview);
  });
})();
