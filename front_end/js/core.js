/* Shared UI and local prototype state. No server data is fabricated here. */
(() => {
  "use strict";
  const paths = {
    home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
    fields:
      '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    chat: '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0Z"/><path d="M7 10h10M7 14h6"/>',
    history: '<path d="M3 11a9 9 0 1 1 2.5 7M3 4v7h7M12 7v5l3 2"/>',
    calendar:
      '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18m-13 5 2 2 5-5"/>',
    compare:
      '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 2v20M6 12l2-2-2-2m12 4-2 2 2 2"/>',
    leaf: '<path d="M20 3C7 2 2 9 6 16s16 2 14-13Z"/><path d="M4 21 16 9M10 15v-5m0 5h5"/>',
    wheat:
      '<path d="M12 22V3m0 15c-5 0-7-3-7-6 4 0 7 2 7 6Zm0-5c-5 0-7-3-7-6 4 0 7 2 7 6Zm0 5c5 0 7-3 7-6-4 0-7 2-7 6Zm0-5c5 0 7-3 7-6-4 0-7 2-7 6Zm0-6c-3-2-3-4 0-6 3 2 3 4 0 6Z"/>',
    arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-11 12a2 2 0 0 0 4 0"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
    cloud: '<path d="M6 18a5 5 0 1 1 1-10 6 6 0 0 1 11 2 4 4 0 1 1 0 8Z"/>',
    rain: '<path d="M6 15a4 4 0 1 1 1-8 6 6 0 0 1 11 2 3 3 0 0 1 0 6M8 18l-1 3m6-3-1 3m6-3-1 3"/>',
    pin: '<path d="M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    upload:
      '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    image:
      '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4m0 3h.01"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    edit: '<path d="m15 4 5 5M4 20l5-1L21 7l-5-5L4 14Z"/>',
    alert: '<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3h.01"/>',
    book: '<path d="M12 5v16M3 3c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2Z"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="m22 2-11 11"/>',
    refresh: '<path d="M20 7a9 9 0 1 0 1 8M20 2v6h-6"/>',
    trash: '<path d="M3 6h18M9 6V3h6v3m-10 0 1 15h12l1-15M10 10v7m4-7v7"/>',
    drop: '<path d="M19 14a7 7 0 0 1-14 0c0-4 7-12 7-12s7 8 7 12Z"/>',
    wind: '<path d="M3 8h12a3 3 0 1 0-3-3M2 12h17a3 3 0 1 1-3 3M4 16h5a3 3 0 1 1-3 3"/>',
  };
  const icon = (name, cls = "") =>
    `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.leaf}</svg>`;
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const uid = () =>
    window.crypto?.randomUUID?.() ||
    `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const today = () =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  const fmt = (value) =>
    value ? String(value).slice(0, 10).replaceAll("-", ".") : "未记录";
  const briefDate = (value) =>
    value
      ? `${Number(value.slice(5, 7))}月${Number(value.slice(8, 10))}日`
      : "未记录";
  const seed = () => ({
    version: 1,
    fields: [
      {
        id: "east",
        name: "东坡示范田",
        location: "河南省 · 郑州市中牟县",
        area: 28.5,
        variety: "郑麦136",
        sowDate: "2025-10-16",
        season: "2025—2026",
        stage: "拔节—孕穗期",
        attention: "待复查",
        cover: "assets/wheat-green.jpg",
        note: "固定采样点 A：田块东侧，沿田埂向内约 10 米。示例档案，品种与生育期仅用于演示。",
        demo: true,
      },
      {
        id: "river",
        name: "河湾试验田",
        location: "河南省 · 新乡市原阳县",
        area: 16,
        variety: "百农207",
        sowDate: "2025-10-18",
        season: "2025—2026",
        stage: "生育期待确认",
        attention: "待补记录",
        cover: "assets/wheat-gold.jpg",
        note: "请补充本季生育期与近期管理记录。封面为示意图。",
        demo: true,
      },
      {
        id: "south",
        name: "南岭观察田",
        location: "河南省 · 许昌市长葛市",
        area: 32,
        variety: "待补充",
        sowDate: "2025-10-20",
        season: "2025—2026",
        stage: "孕穗期",
        attention: "持续观察",
        cover: "assets/wheat-green.jpg",
        note: "示例档案，定期补充全景与叶片近景。",
        demo: true,
      },
    ],
    records: [
      {
        id: "r1",
        fieldId: "east",
        date: "2026-04-11",
        type: "观察",
        title: "首次记录叶片变化",
        note: "示例观察：局部叶尖颜色偏浅。尚缺全田分布与近期管理记录，暂不确定原因。",
        image: "assets/wheat-green.jpg",
        stage: "拔节期",
        demo: true,
      },
      {
        id: "r2",
        fieldId: "east",
        date: "2026-04-14",
        type: "农事",
        title: "补充近期农事记录",
        note: "示例记录：已补充近期田间管理情况。后续需要将实际操作时间与复查结果对应。",
        stage: "拔节期",
        demo: true,
      },
      {
        id: "r3",
        fieldId: "east",
        date: "2026-04-18",
        type: "复查",
        title: "叶片近景复拍，等待全景补充",
        note: "示例复查：已上传一张叶片近景。两次图片拍摄条件尚未确认，不据此判定长势改善或恶化。下一步补拍固定采样点全景。",
        image: "assets/wheat-green.jpg",
        stage: "孕穗期（待确认）",
        demo: true,
      },
      {
        id: "r4",
        fieldId: "river",
        date: "2026-04-16",
        type: "观察",
        title: "建立本季观察档案",
        note: "示例记录：已建立地块档案，等待上传实际田间图片及确认生育期。",
        image: "assets/wheat-gold.jpg",
        stage: "待确认",
        demo: true,
      },
      {
        id: "r5",
        fieldId: "south",
        date: "2026-04-17",
        type: "观察",
        title: "完成一轮常规巡田",
        note: "示例记录：已保留本轮观察。尚无连续实测数据，不生成生长评分。",
        image: "assets/wheat-green.jpg",
        stage: "孕穗期",
        demo: true,
      },
    ],
    tasks: [
      {
        id: "t1",
        fieldId: "east",
        title: "补拍固定采样点全景",
        date: "2026-04-18",
        priority: "优先关注",
        source: "复查记录缺少可比全景",
        note: "尽量保持相近角度与距离，补充异常区域在全田的分布。",
        done: false,
        demo: true,
      },
      {
        id: "t2",
        fieldId: "river",
        title: "确认当前生育期",
        date: "2026-04-18",
        priority: "待补信息",
        source: "地块档案存在缺项",
        note: "结合现场观察确认生育期，避免仅按日期推断。",
        done: false,
        demo: true,
      },
      {
        id: "t3",
        fieldId: "east",
        title: "补充最近一次水肥操作",
        date: "2026-04-19",
        priority: "常规跟踪",
        source: "需要关联农事与后续变化",
        note: "记录实际操作日期和内容；没有发生操作也可以如实记录。",
        done: false,
        demo: true,
      },
      {
        id: "t4",
        fieldId: "south",
        title: "记录低洼区域现场情况",
        date: "2026-04-17",
        priority: "常规跟踪",
        source: "巡田计划",
        note: "示例任务已完成。完成任务不代表地块已经排除所有风险。",
        done: true,
        demo: true,
      },
    ],
    chats: [],
    cases: [],
  });
  const key = "zhimai.frontend.v1";
  let state;
  let storageWarning = false;
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    state =
      saved?.version === 1 &&
      ["fields", "records", "tasks", "chats", "cases"].every((k) =>
        Array.isArray(saved[k]),
      )
        ? saved
        : seed();
  } catch {
    state = seed();
    storageWarning = true;
  }
  const readSetting = (k, fallback) => {
    try {
      return localStorage.getItem(k) || fallback;
    } catch {
      return fallback;
    }
  };
  let mode = readSetting("zhimai.mode", "demo");
  const commit = (fn) => {
    const next = JSON.parse(JSON.stringify(state));
    fn(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
      state = next;
      return true;
    } catch {
      toast(
        "保存失败：浏览器存储不可用或空间不足，请导出档案后重试。",
        "error",
      );
      return false;
    }
  };
  const field = (id) => state.fields.find((f) => f.id === id);
  const records = (id) =>
    state.records
      .filter((r) => r.fieldId === id)
      .reverse()
      .sort((a, b) => b.date.localeCompare(a.date));
  const badge = (text, tone = "green") =>
    `<span class="badge ${tone}">${esc(text)}</span>`;
  const fieldOptions = (selected) =>
    state.fields
      .map(
        (f) =>
          `<option value="${esc(f.id)}" ${f.id === selected ? "selected" : ""}>${esc(f.name)}</option>`,
      )
      .join("");
  const empty = (title, detail, action = "") =>
    `<div class="empty-state">${icon("leaf")}<h3>${esc(title)}</h3><p>${esc(detail)}</p>${action}</div>`;
  function toast(message, tone = "success") {
    const box = document.getElementById("toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = `toast ${tone}`;
    el.setAttribute("role", tone === "error" ? "alert" : "status");
    el.innerHTML = `${icon(tone === "error" ? "alert" : "check")}<span>${esc(message)}</span><button class="icon-btn" aria-label="关闭提示">${icon("close")}</button>`;
    el.querySelector("button").onclick = () => el.remove();
    box.append(el);
    setTimeout(() => el.remove(), 6500);
  }
  let closeHook = null,
    lastFocus = null;
  function closeModal() {
    const d = document.getElementById("appDialog");
    if (d?.open) d.close();
  }
  function modal(title, html, onSubmit, options = {}) {
    const d = document.getElementById("appDialog");
    if (d.open) d.close();
    lastFocus = document.activeElement;
    d.innerHTML = `<form id="dialogForm"><div class="modal-header"><div><span class="eyebrow">ZHIMAI · 智麦</span><h2 id="dialogTitle">${esc(title)}</h2></div><button type="button" class="icon-btn" data-close aria-label="关闭对话框">${icon("close")}</button></div><div class="modal-body">${html}<p class="form-error" id="dialogError" role="alert"></p></div><div class="modal-footer"><button type="button" class="btn" data-close>${options.cancel || "取消"}</button>${onSubmit ? `<button type="submit" class="btn primary">${options.submit || "保存"}</button>` : ""}</div></form>`;
    d.setAttribute("aria-labelledby", "dialogTitle");
    d.classList.toggle("wide", Boolean(options.wide));
    closeHook = options.onClose || null;
    d.showModal();
    d.querySelectorAll("[data-close]").forEach((b) => (b.onclick = closeModal));
    d.onclick = (e) => {
      if (e.target === d) {
        const b = d.getBoundingClientRect();
        if (
          e.clientX < b.left ||
          e.clientX > b.right ||
          e.clientY < b.top ||
          e.clientY > b.bottom
        )
          closeModal();
      }
    };
    const form = d.querySelector("form");
    form.onsubmit = async (e) => {
      e.preventDefault();
      if (!onSubmit) return;
      const btn = form.querySelector("[type=submit]");
      btn.disabled = true;
      try {
        await onSubmit(new FormData(form), d);
      } catch (err) {
        d.querySelector("#dialogError").textContent =
          err.message || "保存失败，请重试。";
      } finally {
        if (btn.isConnected) btn.disabled = false;
      }
    };
    return d;
  }
  const photoFile = async (file) => {
    if (!file?.size) return "";
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type))
      throw new Error("请选择 JPG、PNG 或 WEBP 图片。");
    if (file.size > 2 * 1024 * 1024)
      throw new Error("本地档案图片请控制在 2 MB 以内。");
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("图片读取失败。"));
      reader.readAsDataURL(file);
    });
  };
  const safeImage = (src) =>
    /^(assets\/[\w./-]+|data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+)$/.test(
      src || "",
    )
      ? src
      : "assets/wheat-green.jpg";
  function newField(existingId) {
    const f = field(existingId) || {};
    modal(
      f.id ? "编辑地块档案" : "建立一块田的生长档案",
      `<p class="form-intro">从地块开始，记录这一季的每一次变化。${f.demo ? "当前为示例档案。" : "新档案仅在当前浏览器保存。"}</p><div class="form-grid"><label>地块名称 <span>*</span><input name="name" required maxlength="40" placeholder="例如：东侧一号田" value="${esc(f.name || "")}"></label><label>所在地区 <span>*</span><input name="location" required maxlength="80" placeholder="省 / 市 / 县" value="${esc(f.location || "")}"></label><label>面积（亩）<input name="area" type="number" min="0.01" max="1000000" step="0.01" required value="${esc(f.area || "")}" placeholder="例如：20"></label><label>小麦品种<input name="variety" maxlength="60" placeholder="暂不清楚可留空" value="${esc(f.variety || "")}"></label><label>播种日期<input name="sowDate" type="date" value="${esc(f.sowDate || "")}"></label><label>种植季<input name="season" required maxlength="24" value="${esc(f.season || "2026—2027")}"></label><label>当前生育期<select name="stage">${["生育期待确认", "播种出苗期", "分蘖期", "越冬期", "返青期", "拔节期", "拔节—孕穗期", "孕穗期", "抽穗扬花期", "灌浆期", "成熟期"].map((s) => `<option ${s === f.stage ? "selected" : ""}>${s}</option>`).join("")}</select></label><label>跟踪状态<select name="attention">${["持续观察", "待复查", "待补记录", "本季已结束"].map((s) => `<option ${s === f.attention ? "selected" : ""}>${s}</option>`).join("")}</select></label><label class="full">采样点与备注<textarea name="note" rows="3" maxlength="1000" placeholder="记录固定采样点位置，便于下一次在相近角度拍摄。">${esc(f.note || "")}</textarea></label></div>`,
      (data) => {
        const name = data.get("name").trim(),
          location = data.get("location").trim();
        if (!name || !location) throw new Error("请填写地块名称和所在地区。");
        const id = f.id || uid();
        const updated = {
          ...f,
          id,
          name,
          location,
          area: Number(data.get("area")),
          variety: data.get("variety").trim() || "待补充",
          sowDate: data.get("sowDate"),
          season: data.get("season").trim(),
          stage: data.get("stage"),
          attention: data.get("attention"),
          note: data.get("note").trim(),
          cover: f.cover || "assets/wheat-green.jpg",
          demo: f.demo || false,
        };
        if (!updated.season) throw new Error("请填写种植季。");
        if (
          commit((s) => {
            if (f.id)
              s.fields[s.fields.findIndex((x) => x.id === id)] = updated;
            else s.fields.push(updated);
          })
        ) {
          closeModal();
          toast("地块档案已保存");
          if (!f.id) locationTo(`field.html?id=${encodeURIComponent(id)}`);
          else window.dispatchEvent(new Event("zm:refresh"));
        }
      },
    );
  }
  function newRecord(fieldId, type = "观察", prefill = {}) {
    if (!state.fields.length) {
      newField();
      return;
    }
    modal(
      "记下田间的新变化",
      `<div class="form-grid"><label>所属地块<select name="fieldId">${fieldOptions(fieldId)}</select></label><label>记录日期<input name="date" type="date" required value="${today()}"></label><label>记录类型<select name="type">${["观察", "农事", "复查"].map((t) => `<option ${type === t ? "selected" : ""}>${t}</option>`).join("")}</select></label><label>生育期<input name="stage" maxlength="40" placeholder="不确定时请填写待确认" value="${esc(field(fieldId)?.stage || "")}"></label><label class="full">记录标题<input name="title" required maxlength="100" placeholder="例如：固定采样点 A，补拍叶片近景" value="${esc(prefill.title || "")}"></label><label class="full">现场观察或实际操作<textarea name="note" required rows="4" maxlength="4000" placeholder="描述看见了什么、范围如何，或记录实际发生的农事操作。">${esc(prefill.note || "")}</textarea></label><label class="full file-label">附上一张照片（可选）<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"><small>JPG / PNG / WEBP，最大 2 MB。建议固定位置、相近角度拍摄。</small></label></div>`,
      async (data) => {
        const title = data.get("title").trim(),
          note = data.get("note").trim();
        if (!title || !note) throw new Error("请填写标题和记录内容。");
        const image = await photoFile(data.get("photo"));
        const r = {
          id: uid(),
          fieldId: data.get("fieldId"),
          date: data.get("date"),
          type: data.get("type"),
          stage: data.get("stage").trim(),
          title,
          note,
          image,
          demo: false,
        };
        if (commit((s) => s.records.push(r))) {
          closeModal();
          toast("新记录已加入地块时间线");
          window.dispatchEvent(new Event("zm:refresh"));
        }
      },
    );
  }
  function newTask(fieldId, title = "", note = "") {
    if (!state.fields.length) {
      newField();
      return;
    }
    modal(
      "安排下一次田间行动",
      `<div class="form-grid"><label>所属地块<select name="fieldId">${fieldOptions(fieldId)}</select></label><label>计划日期<input name="date" type="date" required value="${today()}"></label><label class="full">任务名称<input name="title" required maxlength="100" placeholder="例如：补拍固定采样点全景" value="${esc(title)}"></label><label>优先级<select name="priority"><option>常规跟踪</option><option>优先关注</option><option>待补信息</option></select></label><label>任务依据<input name="source" maxlength="160" value="用户创建" placeholder="说明为什么需要这次行动"></label><label class="full">行动说明<textarea name="note" rows="3" maxlength="2000" placeholder="在哪里观察，需要带回什么信息？">${esc(note)}</textarea></label></div>`,
      (data) => {
        const title = data.get("title").trim();
        if (!title) throw new Error("请填写任务名称。");
        if (
          commit((s) =>
            s.tasks.push({
              id: uid(),
              fieldId: data.get("fieldId"),
              date: data.get("date"),
              title,
              priority: data.get("priority"),
              source: data.get("source").trim() || "用户创建",
              note: data.get("note").trim(),
              done: false,
              demo: false,
            }),
          )
        ) {
          closeModal();
          toast("跟踪任务已创建");
          window.dispatchEvent(new Event("zm:refresh"));
        }
      },
    );
  }
  function toggleTask(id) {
    if (
      commit((s) => {
        const t = s.tasks.find((x) => x.id === id);
        if (t) t.done = !t.done;
      })
    ) {
      toast(
        state.tasks.find((t) => t.id === id)?.done
          ? "已标记完成，可在已完成中重新打开"
          : "任务已重新打开",
      );
      window.dispatchEvent(new Event("zm:refresh"));
    }
  }
  function taskDetail(id) {
    const t = state.tasks.find((t) => t.id === id);
    if (!t) return;
    modal(
      t.title,
      `${badge(t.done ? "已完成" : t.priority, t.done ? "green" : "amber")}<dl class="detail-list"><dt>所属地块</dt><dd>${esc(field(t.fieldId)?.name || "未知地块")}</dd><dt>计划日期</dt><dd>${fmt(t.date)}</dd><dt>任务依据</dt><dd>${esc(t.source)}</dd><dt>行动说明</dt><dd>${esc(t.note || "暂无补充说明")}</dd><dt>数据来源</dt><dd>${t.demo ? "历史情境演示" : "本地创建"}</dd></dl>`,
      () => {
        toggleTask(id);
        closeModal();
      },
      { submit: t.done ? "重新打开任务" : "标记完成" },
    );
  }
  const locationTo = (url) => {
    window.location.href = url;
  };
  const download = (name, content, type = "text/markdown;charset=utf-8") => {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  function exportField(id) {
    const f = field(id);
    if (!f) return;
    const text = [
      `# ${f.name} · ${f.season} 生长档案`,
      `地区：${f.location}｜面积：${f.area} 亩｜品种：${f.variety}`,
      `来源：${f.demo ? "示例档案，包含演示记录" : "本地创建档案"}`,
      `备注：${f.note || "无"}`,
      ...records(id).map(
        (r) =>
          `\n## ${r.date} · ${r.title}\n类型：${r.type}｜来源：${r.demo ? "演示" : "用户记录"}\n${r.note}`,
      ),
      "\n## 跟踪任务",
      ...state.tasks
        .filter((t) => t.fieldId === id)
        .map(
          (t) =>
            `- [${t.done ? "x" : " "}] ${t.date} ${t.title}（${t.demo ? "演示" : "用户创建"}）`,
        ),
    ];
    download(`${f.name}-生长档案.md`, text.join("\n\n"));
    toast("文字档案已导出，原始照片请另行保存");
  }
  function settings() {
    modal(
      "选择体验方式",
      `<p class="form-intro">演示模式可以完整体验页面，不会调用模型。连接后端后，智能诊断和历史案例使用实际接口；地块档案与任务仍仅在当前浏览器保存。</p><label class="radio-card"><input type="radio" name="mode" value="demo" ${mode === "demo" ? "checked" : ""}><span><strong>体验演示</strong><small>历史情境、示例回答均明确标注；可创建自己的本地档案。</small></span></label><label class="radio-card"><input type="radio" name="mode" value="live" ${mode === "live" ? "checked" : ""}><span><strong>连接现有后端</strong><small>使用真实图片识别、聊天与历史接口，保留失败与重试状态。</small></span></label><label class="mt">后端地址<input name="baseUrl" type="url" value="${esc(readSetting("zhimai.apiBase", "http://127.0.0.1:8000"))}" placeholder="http://127.0.0.1:8000"></label>`,
      (data) => {
        const url = new URL(data.get("baseUrl"));
        if (
          !["http:", "https:"].includes(url.protocol) ||
          url.username ||
          url.password ||
          url.search ||
          url.hash
        )
          throw new Error("请输入不含账号、查询参数的 HTTP 或 HTTPS 地址。");
        try {
          localStorage.setItem("zhimai.mode", data.get("mode"));
          localStorage.setItem("zhimai.apiBase", url.href.replace(/\/$/, ""));
        } catch {
          throw new Error("浏览器不允许保存设置。");
        }
        closeModal();
        window.location.reload();
      },
      { submit: "保存并应用" },
    );
  }
  function globalSearch() {
    const d = modal(
      "查找地块与任务",
      `<label class="search-box">${icon("search")}<input id="globalSearch" placeholder="输入地块、品种或任务关键词" autocomplete="off" aria-label="全局搜索"></label><div id="searchResults" class="search-results"></div>`,
      null,
      { cancel: "关闭" },
    );
    const input = d.querySelector("input");
    const update = () => {
      const q = input.value.trim().toLowerCase();
      const fs = state.fields.filter((f) =>
        `${f.name}${f.location}${f.variety}`.toLowerCase().includes(q),
      );
      const ts = state.tasks.filter((t) =>
        `${t.title}${t.note}`.toLowerCase().includes(q),
      );
      d.querySelector("#searchResults").innerHTML =
        fs
          .map(
            (f) =>
              `<a href="field.html?id=${encodeURIComponent(f.id)}">${icon("fields")}<span><strong>${esc(f.name)}</strong><small>${esc(f.location)}</small></span>${icon("arrow")}</a>`,
          )
          .join("") +
          ts
            .map(
              (t) =>
                `<button type="button" data-result-task="${esc(t.id)}">${icon("calendar")}<span><strong>${esc(t.title)}</strong><small>${esc(field(t.fieldId)?.name)} · ${t.done ? "已完成" : "待完成"}</small></span>${icon("arrow")}</button>`,
            )
            .join("") ||
        empty("没有找到匹配结果", "试试地块名、品种或任务中的关键词。");
    };
    update();
    input.oninput = update;
    d.addEventListener("click", (e) => {
      const b = e.target.closest("[data-result-task]");
      if (b) taskDetail(b.dataset.resultTask);
    });
    input.focus();
  }
  const pageInfo = {
    dashboard: ["今日工作台", "把每一季的变化，变成有依据的行动。"],
    fields: ["我的地块", "一块田，一份持续生长的档案。"],
    field: ["地块生长档案", "沿着时间，看见变化。"],
    diagnosis: ["智能诊断", "从一张照片，开始一次有依据的观察。"],
    history: ["诊断历史", "让每一次判断都有迹可循。"],
    tasks: ["跟踪任务", "让建议有后续，让观察有回音。"],
    compare: ["生长对比", "把两次观察放在一起，认真看见变化。"],
  };
  function shell() {
    const page = document.body.dataset.page;
    const info = pageInfo[page] || pageInfo.dashboard;
    const active = page === "field" ? "fields" : page;
    const nav = [
      ["dashboard", "home", "今日工作台", "index.html"],
      ["fields", "fields", "我的地块", "fields.html"],
      ["diagnosis", "chat", "智能诊断", "diagnosis.html"],
      ["compare", "compare", "生长对比", "compare.html"],
      ["tasks", "calendar", "跟踪任务", "tasks.html"],
      ["history", "history", "诊断历史", "history.html"],
    ];
    document.getElementById("app").innerHTML =
      `<a href="#mainContent" class="skip-link">跳到主要内容</a><button class="sidebar-scrim" aria-label="关闭导航"></button><aside class="sidebar" id="sidebar"><a href="index.html" class="brand"><span class="brand-mark">${icon("wheat")}</span><span><b>智麦<span class="brand-dot">.</span></b><small>小麦全周期生长助手</small></span></a><div class="sidebar-label">我的农田工作空间</div><nav aria-label="主导航">${nav.map(([key, ic, title, url]) => `<a href="${url}" ${key === active ? 'aria-current="page"' : ""} class="nav-item ${key === active ? "active" : ""}">${icon(ic)}<span>${title}</span>${key === "tasks" ? `<span class="nav-count">${state.tasks.filter((t) => !t.done).length}</span>` : ""}</a>`).join("")}</nav><div class="sidebar-bottom"><div class="season-note">${icon("leaf")}<span>记录生长，陪伴每一季<small>从田间观察，到持续跟踪</small></span></div><button class="help-btn" data-action="help">${icon("help")} 使用指南 ${icon("arrow")}</button><div class="profile"><span class="avatar">麦</span><span><strong>我的种植空间</strong><small>本地体验 · 仅此设备保存</small></span><button class="icon-btn" aria-label="打开体验设置" data-action="settings">${icon("down")}</button></div></div></aside><div class="main-wrapper"><header class="topbar"><div class="topbar-left"><button class="icon-btn menu-toggle" aria-label="展开导航" aria-expanded="false">${icon("menu")}</button><span class="breadcrumb">我的工作空间 ${icon("chevron")} <strong>${info[0]}</strong></span></div><div class="topbar-actions"><button class="search-trigger" data-action="search">${icon("search")}<span>搜索地块、任务</span><kbd>⌘ K</kbd></button><button class="mode-pill ${mode === "demo" ? "demo" : "live"}" data-action="settings"><i></i>${mode === "demo" ? "演示模式" : "后端连接模式"}</button><button class="icon-btn notification-btn" aria-label="查看待完成任务" data-action="notifications">${icon("bell")}<span class="notification-dot" ${state.tasks.some((t) => !t.done) ? "" : "hidden"}></span></button><span class="top-avatar">麦</span></div></header><main id="mainContent" class="page-content" tabindex="-1"></main><footer class="page-footer"><span>智麦 ZHIMAI <i>·</i> 记录每一份生长</span><span>${mode === "demo" ? "演示情境与本地记录 · 非实时监测" : "地块与任务为本地记录 · 诊断与历史可连接后端"}</span></footer></div><dialog id="appDialog"></dialog><div id="toasts" class="toasts" aria-live="polite"></div>`;
    const d = document.getElementById("appDialog");
    d.addEventListener("close", () => {
      closeHook?.();
      closeHook = null;
      lastFocus?.focus?.();
    });
    if (storageWarning)
      toast(
        "无法读取已保存档案，当前展示示例。请检查浏览器存储设置。",
        "error",
      );
  }
  function help() {
    modal(
      "从一块田，开始记录这一季",
      `<div class="guide-step"><span>01</span><div><h3>建立地块档案</h3><p>记录位置、品种与播种日期。选定固定采样点，让后续照片更容易比较。</p></div></div><div class="guide-step"><span>02</span><div><h3>观察、提问，再决定下一步</h3><p>上传图片只进行识别。输入问题并点击发送后，才开始正式对话。演示回复不代表实际模型判断。</p></div></div><div class="guide-step"><span>03</span><div><h3>把建议变成可跟踪的行动</h3><p>创建复查任务，补充现场记录；将两次观察并排查看，记录变化与仍待确认的信息。</p></div></div><div class="notice">${icon("book")}<span>示例照片不代表同一地块连续实拍。演示天气、地块及回答均非实时数据；新建档案与任务仅在当前浏览器保存，建议定期导出。</span></div>`,
      null,
      { cancel: "开始体验" },
    );
  }
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const a = el.dataset.action;
    if (a === "settings") settings();
    if (a === "search") globalSearch();
    if (a === "help") help();
    if (a === "new-field") newField();
    if (a === "new-record") newRecord(el.dataset.field);
    if (a === "new-task") newTask(el.dataset.field);
    if (a === "task-detail") taskDetail(el.dataset.id);
    if (a === "toggle-task") toggleTask(el.dataset.id);
    if (a === "notifications") {
      const pending = state.tasks.filter((t) => !t.done);
      modal(
        "待完成的跟踪任务",
        pending.length
          ? pending
              .map(
                (t) =>
                  `<button type="button" class="notification-item" data-action="task-detail" data-id="${esc(t.id)}">${icon("calendar")}<span><strong>${esc(t.title)}</strong><small>${esc(field(t.fieldId)?.name)} · ${fmt(t.date)}${t.demo ? " · 演示" : ""}</small></span>${icon("arrow")}</button>`,
              )
              .join("")
          : empty("暂时没有待办", "新建跟踪任务后，会在这里集中显示。"),
        null,
        { cancel: "关闭" },
      );
    }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
      e.preventDefault();
      globalSearch();
    }
    if (e.key === "Escape") {
      document.body.classList.remove("nav-open");
      document
        .querySelector(".menu-toggle")
        ?.setAttribute("aria-expanded", "false");
    }
  });
  window.ZM = {
    icon,
    esc,
    uid,
    today,
    fmt,
    briefDate,
    get state() {
      return state;
    },
    get mode() {
      return mode;
    },
    commit,
    field,
    records,
    badge,
    fieldOptions,
    empty,
    toast,
    modal,
    closeModal,
    newField,
    newRecord,
    newTask,
    toggleTask,
    taskDetail,
    safeImage,
    exportField,
    download,
    shell,
    readSetting,
  };
})();
