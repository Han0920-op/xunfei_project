/* Free conversation adapter. The backend model chooses answers and tools.
 * No client-side diagnostic questionnaire or fabricated model/tool output. */
(() => {
  "use strict";
  const S = window.FarmerStore;
  const toolNames = {
    get_weather: "查询天气",
    search_knowledge: "检索小麦资料",
    check_pesticide: "核对农药登记",
  };
  function create() {
    return {
      id: S.id(),
      kind: "agent",
      step: "chat",
      title: "和智麦聊聊",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      archived: false,
      demo: false,
      facts: {},
      photos: [],
      messages: [],
      actions: [],
      followups: [],
      followupDate: "",
    };
  }
  function startMedicine(previous) {
    const t = previous ? structuredClone(previous) : create();
    t.kind = "agent";
    t.step = "chat";
    delete t.pendingFollowup;
    t.messages.push({
      id: S.id(),
      role: "assistant",
      type: "local-note",
      text: "直接发包装上的登记证号，或说明你想核对什么。智麦会按情况查询登记资料；标签照片需要先确认识别出的号码。",
    });
    return t;
  }
  function startFollowup(previous) {
    const t = structuredClone(previous);
    t.archived = false;
    t.kind = "agent";
    t.step = "chat";
    t.pendingFollowup = true;
    return t;
  }
  function history(previous) {
    if (!previous) return [];
    return (previous.messages || [])
      .filter((m) => m.role === "user" || m.type === "agent")
      .map((m) => {
        if (m.role === "user")
          return {
            role: "user",
            content: (
              m.text ||
              (m.photoId ? "此前上传过一张照片，本轮未重新上传。" : "")
            ).slice(0, 2000),
          };
        const notes = [];
        const observations = (m.vision || [])
          .filter((v) => v.status === "ok" && v.content)
          .map((v) => String(v.content).slice(0, 700));
        if (observations.length)
          notes.push(
            "【此前该轮图片的初步观察，非本轮新识别，未确诊】" +
              observations.join("；"),
          );
        for (const t of m.toolResults || []) {
          const r = t.result || {};
          if (t.tool === "get_weather")
            notes.push(
              "【历史天气记录，有日期限制，不是本轮实时天气，需按需重新查询】" +
                JSON.stringify({
                  status: r.status,
                  location: r.location,
                  source: r.source,
                  report_time: r.report_time || r.reporttime,
                  queried_at: r.queried_at,
                  requested_date: r.requested_date,
                  message: r.message,
                  note: r.note,
                  forecast: r.forecast,
                }).slice(0, 500),
            );
          else if (t.tool === "search_knowledge")
            notes.push(
              "【此前检索参考，待审校】" +
                JSON.stringify({
                  status: r.status,
                  retrieved_at: r.retrieved_at,
                  results: (r.results || []).slice(0, 2).map((x) => ({
                    topic: x.topic,
                    quote: String(x.quote || "").slice(0, 150),
                    paragraph: x.paragraph,
                    source: x.source?.title,
                  })),
                }).slice(0, 500),
            );
          else if (t.tool === "check_pesticide")
            notes.push(
              "【此前登记核对记录，不能提升为当前施药许可】" +
                JSON.stringify({
                  status: r.status,
                  heading: r.heading,
                  use_decision: r.use_decision,
                  recommendation_allowed: r.recommendation_allowed,
                  checked_at: r.checked_at,
                  source: r.source?.url,
                }).slice(0, 500),
            );
        }
        notes.push(
          "【此前回答】（模型曾给出的回复，可能错误，不代表用户确认）" +
            String(m.text || "").slice(0, 1200),
        );
        return {
          role: "assistant",
          content: notes.join("\n\n").slice(0, 2000),
        };
      })
      .filter((m) => m.content)
      .slice(-40);
  }
  function normalizeResult(value) {
    if (typeof value !== "string") return value;
    try {
      return JSON.parse(value);
    } catch {
      return {
        status: "unavailable",
        note: "工具没有返回可读取的结构化结果。",
      };
    }
  }
  async function respond(previous, input, signal) {
    const t = previous ? structuredClone(previous) : create();
    const text = String(input.text || "").trim();
    const controller = new AbortController();
    let reader = null;
    const abort = () => {
      controller.abort();
      reader?.cancel().catch(() => {});
    };
    if (signal?.aborted) abort();
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, 180000);
    const form = new FormData();
    form.set("message", text);
    form.set("history", JSON.stringify(history(previous)));
    if (input.file) form.set("image", input.file, input.file.name);
    let answer = "",
      done = false,
      hasFinalAnswer = false,
      review = null;
    const toolCalls = [],
      toolResults = [],
      vision = [];
    const progress = (message) => input.onProgress?.(message);
    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (!response.ok) {
        let message =
          "暂时连接不上智麦服务，请确认通过后端启动页面。输入内容仍保留，可重试。";
        try {
          const error = await response.json();
          if (typeof error.detail === "string") message = error.detail;
        } catch (_) {}
        throw new Error(message);
      }
      if (
        !response.body ||
        !response.headers.get("content-type")?.includes("text/event-stream")
      )
        throw new Error("智麦服务没有返回完整对话，请稍后重试。");
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const consume = (block) => {
        const data = block
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data) return;
        let event;
        try {
          event = JSON.parse(data);
        } catch {
          throw new Error("对话数据未能读取，请重新发送。");
        }
        if (event.type === "error")
          throw new Error(event.message || "智麦没有完成这次回答，请重试。");
        if (event.type === "status") progress(event.message || "智麦正在处理…");
        if (event.type === "vision_result") {
          vision.push(event);
          progress(
            event.status === "ok"
              ? "已取得图片观察，正在结合上下文分析…"
              : "图片暂未读清，正在结合你的描述…",
          );
        }
        if (event.type === "tool_call") {
          toolCalls.push({ tool: event.tool, args: event.args || {} });
          progress(`${toolNames[event.tool] || "调用工具"}…`);
        }
        if (event.type === "tool_result") {
          toolResults.push({
            tool: event.tool,
            result: normalizeResult(event.result),
          });
          progress(`${toolNames[event.tool] || "工具"}已返回，正在整理回答…`);
        }
        if (event.type === "answer_review") {
          review = {
            status: event.status,
            issue_codes: event.issue_codes || [],
          };
        }
        if (event.type === "answer_delta") {
          answer += String(event.content || "");
          input.onDelta?.(answer);
        }
        // Complete answer replaces preview; never append it a second time.
        if (event.type === "answer") {
          hasFinalAnswer = true;
          answer = String(event.content || "");
          input.onDelta?.(answer);
        }
        if (event.type === "done") done = true;
      };
      while (true) {
        const chunk = await reader.read();
        if (controller.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        buffer += chunk.done
          ? decoder.decode()
          : decoder.decode(chunk.value, { stream: true });
        buffer = buffer.replaceAll("\r\n", "\n");
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) >= 0) {
          consume(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
        }
        if (chunk.done) {
          if (buffer.trim()) consume(buffer);
          break;
        }
      }
      if (!done || !hasFinalAnswer || !answer.trim())
        throw new Error(
          "本次对话中断，尚未取得完整回答。输入和照片仍保留，请重试。",
        );
      t.kind = "agent";
      t.step = "chat";
      t.demo = false;
      t.archived = false;
      t.updatedAt = new Date().toISOString();
      t.facts ||= {};
      t.photos ||= [];
      t.messages ||= [];
      t.actions ||= [];
      t.followups ||= [];
      if (!previous || t.title === "和智麦聊聊")
        t.title = (text || "照片中的小麦情况").slice(0, 36);
      if (input.photo) t.photos.push(input.photo);
      t.messages.push({
        id: S.id(),
        role: "user",
        text: text || "帮我看看这张照片",
        photoId: input.photo?.id,
      });
      t.messages.push({
        id: S.id(),
        role: "assistant",
        type: "agent",
        text: answer.trim(),
        toolCalls,
        toolResults,
        vision,
        review,
      });
      if (t.pendingFollowup) {
        t.followups.push({
          id: S.id(),
          date: S.date(),
          outcome: "自由对话复查",
          note: text,
          photoId: input.photo?.id || null,
        });
        t.followupDate = "";
        delete t.pendingFollowup;
      }
      return t;
    } catch (error) {
      if (error.name === "AbortError")
        throw new Error(
          signal?.aborted
            ? "已停止生成，输入和照片仍保留。未完成的回答没有保存。"
            : "等待超时，输入和照片仍保留，请重试。",
        );
      if (error instanceof TypeError)
        throw new Error(
          "暂时连接不上智麦服务，请检查网络后重试。输入和照片仍保留。",
        );
      throw error;
    } finally {
      controller.abort();
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  }
  window.FarmerAssistant = {
    create,
    startMedicine,
    startFollowup,
    respond,
    history,
  };
})();
