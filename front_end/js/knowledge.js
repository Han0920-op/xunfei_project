/* Text-only retrieval. Pictures and local record IDs are never uploaded here. */
(() => {
  "use strict";
  window.KnowledgeClient = {
    async assist(facts, signal) {
      const controller = new AbortController();
      const abort = () => controller.abort();
      if (signal?.aborted) abort();
      signal?.addEventListener("abort", abort, { once: true });
      const timer = setTimeout(abort, 8000);
      try {
        const response = await fetch("/api/knowledge/assist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            description: [facts.description, facts.additionalNote]
              .filter(Boolean)
              .join("；")
              .slice(0, 4000),
            distribution: String(facts.distribution || "").slice(0, 500),
            stage: String(facts.stage || "").slice(0, 500),
          }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("知识检索暂不可用");
        const result = await response.json();
        if (
          !["found", "no_match", "unavailable"].includes(result.status) ||
          !Array.isArray(result.results)
        )
          throw new Error("知识资料不完整");
        return result;
      } catch (error) {
        if (signal?.aborted) throw error;
        return {
          status: "unavailable",
          results: [],
          notice:
            "本次没有取得知识库依据，未识别照片。请补充异常部位和全株照片，必要时请农技人员现场复核。",
        };
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener("abort", abort);
      }
    },
  };
})();
