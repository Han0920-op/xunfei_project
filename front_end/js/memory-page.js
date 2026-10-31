(async () => {
  const { esc, icon, modal, close, toast } = FarmerUI;
  document.getElementById("app").innerHTML = AppShell.markup("history");
  const root = document.getElementById("main");
  root.classList.add("personal-main");
  const api = MemoryUI.api,
    caseId = new URLSearchParams(location.search).get("case");
  let profile,
    caseData,
    caseList = [],
    query = "";
  function factCard(f) {
    return `<article class="personal-card"><span class="personal-badge">${f.case_id ? "本次案例事实" : "用户长期资料"} · 你已确认</span><h2>${esc(f.label)}</h2><p class="personal-note">${esc(f.content)}</p><div class="card-actions"><button class="text-button" data-edit-fact="${esc(f.id)}">更正</button><button class="text-button" data-delete-fact="${esc(f.id)}">删除记忆</button></div></article>`;
  }
  async function render() {
    profile = await api("profile");
    caseData = caseId ? await api("cases/" + encodeURIComponent(caseId)) : null;
    caseList = query
      ? await api("search", "POST", { query })
      : await api("cases");
    root.innerHTML = `<div class="personal-heading"><div><span class="page-eyebrow">${icon("book")}你确认的资料，持续帮助之后的判断</span><h1>${caseData ? esc(caseData.title) : "长期记忆"}</h1><p>用户描述、图片观察、模型判断与已确认事实分别保存。</p></div><button class="button primary" data-add-fact>${icon("plus")}添加确认资料</button></div><p class="error" id="memoryError" role="alert"></p><div class="personal-banner"><p>新会话会按需读取已确认资料；旧案例先由你确认关联。<small>当前仅保存案例文字、观察摘要和查询依据，照片仍在原设备。</small></p></div>
 <h2 class="memory-section-title">${caseData ? "本次已确认事实" : "用户长期资料"}</h2><div class="personal-grid">${(caseData?.facts || profile.facts).map(factCard).join("") || '<p class="personal-note">尚未保存确认资料。可以告诉智麦“请记住……”，确认后再入库。</p>'}</div>
 ${
   caseData
     ? `<h2 class="memory-section-title">案例时间线</h2><a class="button secondary" href="index.html?case=${encodeURIComponent(caseData.id)}">确认是这次，继续咨询</a>${caseData.turns.map((t) => `<article class="personal-card memory-timeline"><small>${esc(t.created_at)}</small><span class="personal-badge">用户描述 · 未独立核实</span><p>${esc(t.user.text)}</p>${(t.assistant.vision || []).map((v) => `<span class="personal-badge amber-badge">视觉观察 · 可能有误</span><p>${esc(v.content)}</p>`).join("")}<span class="personal-badge muted-badge">模型判断 · 未确诊</span><p>${esc(t.assistant.text)}</p></article>`).join("")}`
     : `<h2 class="memory-section-title">服务端案例</h2><label class="personal-search">${icon("search")}<input id="caseSearch" type="search" placeholder="按症状查旧案例" aria-label="搜索服务端案例" value="${esc(query)}"></label><div id="serverCases"></div><h2 class="memory-section-title">旧设备记录</h2><p class="personal-note">选择“同步文字”才会上传旧记录；演示记录不入库，不上传旧照片。</p><div class="personal-grid">${
         FarmerStore.records()
           .filter((r) => !r.demo && !caseList.some((c) => c.id === r.id))
           .map(
             (r) =>
               `<article class="personal-card"><h2>${esc(r.title)}</h2><button class="button secondary" data-import="${esc(r.id)}">同步文字</button></article>`,
           )
           .join("") || '<p class="personal-note">没有待同步的本机记录。</p>'
       }</div>`
 }
 <h2 class="memory-section-title">身份恢复</h2><p class="personal-note">在新设备打开智麦后可用恢复码找回同一份服务端资料。请离线保管恢复码，不要发给别人；本机照片不会随之迁移。${profile.recovery_enabled ? "已设置恢复码；重置后旧码失效。" : "尚未设置恢复码。"}</p><button class="button secondary" id="recovery">${profile.recovery_enabled ? "重置恢复码" : "生成恢复码"}</button><button class="button secondary" id="restore">用恢复码找回资料</button><p><a class="text-button" href="history.html">返回我的记录</a></p>`;
    if (!caseData) {
      drawCases();
      let timer;
      document.getElementById("caseSearch").oninput = (e) => {
        query = e.target.value;
        clearTimeout(timer);
        timer = setTimeout(async () => {
          try {
            caseList = query
              ? await api("search", "POST", { query })
              : await api("cases");
            drawCases();
          } catch (e) {
            fail(e);
          }
        }, 250);
      };
    }
  }
  function drawCases() {
    document.getElementById("serverCases").innerHTML =
      `<div class="personal-grid">${caseList.map((c) => `<article class="personal-card"><h2>${esc(c.title)}</h2><p class="personal-note">${esc(c.summary)}</p><small>${esc(c.updated_at.slice(0, 10))} · ${c.archived ? "已结束" : "进行中"}</small><a class="button secondary" href="memory.html?case=${encodeURIComponent(c.id)}">查看事实与时间线</a><div class="card-actions"><a href="index.html?case=${encodeURIComponent(c.id)}">确认这次，继续咨询</a><button class="text-button" data-edit-case="${esc(c.id)}">更正标题</button><button class="text-button" data-delete-case="${esc(c.id)}">删除案例</button></div></article>`).join("") || '<p class="personal-note">没有相关服务端案例。</p>'}</div>`;
  }
  function fail(e) {
    const el = document.getElementById("memoryError");
    if (el) el.textContent = e.message;
    else root.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
  function editFact(f = {}) {
    const scope = caseData?.id || f.case_id || "";
    modal(
      f.id ? "更正确认资料" : "添加确认资料",
      `<p>仅记录你确认的情况，不把模型猜测当作事实。</p><label>资料名称<input name="label" required maxlength="80" placeholder="例如：常用地区" value="${esc(f.label || "")}"></label><label>具体内容<textarea name="content" required maxlength="2000">${esc(f.content || "")}</textarea></label>`,
      async (fd) => {
        await api("facts/" + (f.id || FarmerStore.id()), "PUT", {
          label: fd.get("label"),
          content: fd.get("content"),
          case_id: scope,
        });
        close();
        await render();
      },
      "确认记住",
    );
  }
  root.onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.hasAttribute("data-add-fact")) editFact();
      if (b.dataset.editFact)
        editFact(
          [...(profile.facts || []), ...(caseData?.facts || [])].find(
            (f) => f.id === b.dataset.editFact,
          ),
        );
      if (b.dataset.deleteFact)
        modal(
          "删除记忆",
          "<p>删除后不会继续作为已确认背景提供给智麦；原聊天文字仍属于历史记录。</p>",
          async () => {
            await api(
              "facts/" + encodeURIComponent(b.dataset.deleteFact),
              "DELETE",
            );
            close();
            await render();
          },
          "确认删除",
        );
      if (b.dataset.deleteCase)
        modal(
          "删除案例",
          "<p>删除服务端对话、观察和本次事实，同时移除此设备上的对应记录。无法撤销。</p>",
          async () => {
            await api(
              "cases/" + encodeURIComponent(b.dataset.deleteCase),
              "DELETE",
            );
            if (FarmerStore.get(b.dataset.deleteCase))
              FarmerStore.remove(b.dataset.deleteCase);
            close();
            await render();
          },
          "确认删除",
        );
      if (b.dataset.editCase) {
        const c = caseList.find((x) => x.id === b.dataset.editCase);
        modal(
          "更正案例标题",
          `<label>标题<input name="title" required maxlength="80" value="${esc(c.title)}"></label>`,
          async (fd) => {
            await api("cases/" + encodeURIComponent(c.id), "PATCH", {
              title: fd.get("title"),
              archived: c.archived,
            });
            close();
            await render();
          },
          "保存标题",
        );
      }
      if (b.dataset.import) {
        const r = FarmerStore.get(b.dataset.import);
        modal(
          "同步旧案例文字",
          `<p>将上传“${esc(r.title)}”的文字记录。旧照片不会上传，历史模型判断仍标为未核实。</p>`,
          async () => {
            await api("import", "POST", {
              id: r.id,
              title: r.title.slice(0, 80),
              demo: Boolean(r.demo),
              messages: r.messages
                .filter((m) => ["user", "assistant"].includes(m.role))
                .map((m) => ({ id: m.id, role: m.role, text: m.text || "" })),
            });
            close();
            await render();
          },
          "确认同步",
        );
      }
      if (b.id === "recovery")
        modal(
          "生成或重置恢复码",
          "<p>恢复码相当于访问资料的凭据，请离线保管。生成后原恢复码失效。</p>",
          async () => {
            const result = await api("recovery", "POST");
            modal(
              "请保存恢复码",
              `<p>请复制并离线保存，关闭后不再显示。</p><textarea readonly aria-label="恢复码">${esc(result.code)}</textarea>`,
            );
          },
          "生成恢复码",
        );
      if (b.id === "restore")
        modal(
          "恢复服务端资料",
          '<p>将切换到恢复码所属身份。当前本机照片和旧记录不会自动删除或迁移，请在个人设备操作。</p><label>恢复码<input name="code" type="password" required autocomplete="off"></label>',
          async (fd) => {
            await api("restore", "POST", { code: fd.get("code") });
            location.replace("memory.html");
          },
          "确认恢复",
        );
    } catch (e) {
      fail(e);
    }
  };
  try {
    await window.PersonalReady;
    await render();
  } catch (e) {
    fail(e);
  }
})();
