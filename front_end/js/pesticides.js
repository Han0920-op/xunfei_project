/* Same-origin adapter. Only user-confirmed text fields leave this device. */
(() => {
  "use strict";
  const statuses = new Set([
    "source_unavailable",
    "not_in_local_catalog",
    "needs_review",
    "mismatch",
    "fields_match",
  ]);
  window.PesticideClient = {
    async check(number, target, signal) {
      const controller = new AbortController();
      const abort = () => controller.abort();
      if (signal?.aborted) abort();
      signal?.addEventListener("abort", abort, { once: true });
      const timer = setTimeout(abort, 10000);
      try {
        const response = await fetch("/api/pesticides/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            registration_number: number,
            crop: "小麦",
            target,
          }),
          signal: controller.signal,
        });
        if (response.status === 422)
          throw new Error(
            "请核对登记号格式，只填写包装上的完整 PD、EX 或 LS 编号；点击下方“重新核对登记号”可修改。",
          );
        if (!response.ok)
          throw new Error(
            "用药核对服务暂不可用，请确认已通过后端启动页面。内容已保留，可重试。",
          );
        const result = await response.json();
        if (
          !statuses.has(result.status) ||
          typeof result.heading !== "string" ||
          typeof result.summary !== "string" ||
          !Array.isArray(result.checks)
        )
          throw new Error("核对服务返回信息不完整，请稍后重试。");
        return result;
      } catch (error) {
        if (error.name === "AbortError")
          throw new Error("查询已取消或超时，内容已保留，请重试。");
        if (error instanceof TypeError)
          throw new Error(
            "暂时连接不上用药核对服务，请检查网络后重试。内容已保留。",
          );
        throw error;
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener("abort", abort);
      }
    },
  };
})();
