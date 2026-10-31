/* Explicit memory confirmation and case selection; never infer facts from prose. */
(() => {
  const { esc, icon } = FarmerUI;
  const drafts = new Map(),
    states = new Map();
  async function api(path, method = "GET", body) {
    await window.PersonalReady;
    const r = await fetch("/api/memory/" + path, {
      method,
      headers: { "Content-Type": "application/json", "X-Zhimai-Personal": "1" },
      cache: "no-store",
      body: body ? JSON.stringify(body) : undefined,
    });
    const result = await r.json();
    if (!r.ok)
      throw Error(
        typeof result.detail === "string" ? result.detail : "记忆资料暂不可用",
      );
    return result;
  }
  function cards(recordId, message) {
    return (message.toolResults || [])
      .map((t, index) => {
        const r = t.result || {};
        if (
          ["search_user_cases", "get_case_history"].includes(t.tool) &&
          r.status === "needs_confirmation" &&
          r.cases?.length
        )
          return `<section class="reminder-draft memory-card"><h3>${icon("history")}这是之前哪次问题？</h3><p>先确认是否为同一次问题，再继续读取旧案例。</p>${r.cases.map((c) => `<div class="memory-candidate"><strong>${esc(c.title)}</strong><p>${esc(c.summary)}</p><small>${esc(String(c.updated_at || "").slice(0, 10))} · 历史用户描述</small><a class="button secondary" href="index.html?case=${encodeURIComponent(c.id)}">是这次，继续这个案例</a></div>`).join("")}<p>都不是的话，可以直接继续描述，作为新问题。</p></section>`;
        if (t.tool !== "prepare_memory_fact" || r.status !== "draft") return "";
        const key = recordId + "-" + message.id + (index ? "-" + index : "");
        const body = {
          label: r.label,
          content: r.content,
          case_id: r.scope === "case" ? recordId : "",
        };
        drafts.set(key, { body, factId: r.existing_fact_id || key });
        const state = states.get(key);
        return `<section class="reminder-draft memory-card"><h3>${icon("book")}确认记住这条资料</h3><p>${r.scope === "case" ? "仅用于这次案例" : "用于今后的新会话"} · 用户确认后保存</p><strong>${esc(r.label)}</strong><p>${esc(r.content)}</p><button type="button" class="button primary" data-save-memory="${esc(key)}" ${state === "saved" ? "disabled" : ""}>${state === "saved" ? "已记住" : "确认记住"}</button><a class="button secondary" href="memory.html${body.case_id ? "?case=" + encodeURIComponent(body.case_id) : ""}">查看和更正记忆</a><p role="status" data-memory-status></p></section>`;
      })
      .join("");
  }
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-save-memory]");
    if (!b) return;
    const key = b.dataset.saveMemory;
    const draft = drafts.get(key);
    const body = draft?.body;
    if (!body || states.get(key) === "saving" || states.get(key) === "saved")
      return;
    states.set(key, "saving");
    b.disabled = true;
    try {
      await api("facts/" + encodeURIComponent(draft.factId), "PUT", body);
      states.set(key, "saved");
      b.textContent = "已记住";
      b.closest("section").querySelector("[data-memory-status]").textContent =
        "已保存为你确认的资料，可以随时更正或删除。";
    } catch (error) {
      states.delete(key);
      b.disabled = false;
      b.closest("section").querySelector("[data-memory-status]").textContent =
        error.message;
    }
  });
  function fromCase(c) {
    const old = FarmerStore.get(c.id),
      record = old ? structuredClone(old) : FarmerAssistant.create();
    record.id = c.id;
    record.title = c.title;
    record.createdAt = c.created_at;
    record.updatedAt = c.updated_at;
    record.archived = c.archived;
    record.serverMemory = { saved: true, case_id: c.id };
    const local = new Map((old?.messages || []).map((m) => [m.id, m]));
    record.messages = c.turns
      .flatMap((t) => [t.user, t.assistant])
      .map((m) => ({
        ...m,
        ...(local.get(m.id)?.photoId
          ? { photoId: local.get(m.id).photoId }
          : {}),
      }));
    // Photos already on this device remain accessible, but are not fetched from server.
    return record;
  }
  document.addEventListener("DOMContentLoaded", async () => {
    if (document.body.dataset.screen === "chat") {
      const id = new URLSearchParams(location.search).get("case");
      if (!id) return;
      try {
        const c = await api("cases/" + encodeURIComponent(id));
        FarmerStore.save(fromCase(c));
        location.replace("index.html?record=" + encodeURIComponent(c.id));
      } catch (error) {
        FarmerUI.modal(
          "无法打开案例",
          `<p>${esc(error.message)}</p><a href="memory.html">查看当前身份的案例</a>`,
        );
      }
    }
  });
  async function loadCaseList() {
    const target = document.getElementById("serverMemoryCases");
    if (!target) return;
    try {
      const cases = await api("cases");
      if (!target.isConnected) return;
      const local = new Set(FarmerStore.records().map((r) => r.id));
      const extra = cases.filter((c) => !local.has(c.id));
      target.innerHTML =
        '<h2 class="memory-section-title">服务端案例</h2>' +
        extra
          .map(
            (c) =>
              `<article class="record-row"><a class="record-main" href="index.html?case=${encodeURIComponent(c.id)}"><div><span class="record-date">${esc(c.updated_at.slice(0, 10))} · 服务端保存</span><h2>${esc(c.title)}</h2><p>点击确认并继续这次案例；原照片仍在原设备。</p></div></a></article>`,
          )
          .join("") +
        (extra.length
          ? ""
          : '<p class="personal-note">没有其他设备保存的案例。可在长期记忆中查看和整理全部服务端案例。</p>');
    } catch {
      if (target.isConnected)
        target.innerHTML =
          '<p class="personal-note">暂未连接服务端案例；本机记录仍可查看。</p>';
    }
  }
  window.MemoryUI = { cards, api, fromCase, loadCaseList };
})();
