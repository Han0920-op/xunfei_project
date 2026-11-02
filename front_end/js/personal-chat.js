/* Carry the selected owned medicine, not an unspecified request to inspect all. */
(() => {
  window.PersonalReady ||= fetch("/api/personal/session");
  document.addEventListener("DOMContentLoaded", async () => {
    const selected = new URLSearchParams(location.search).get("medicine");
    if (!selected) return;
    try {
      await window.PersonalReady;
      const r = await fetch("/api/personal/medicines", { cache: "no-store" });
      if (!r.ok) throw Error();
      const rows = await r.json(),
        m = rows.find((x) => x.id === selected);
      if (!m) {
        FarmerUI.toast(
          "这条农药记录已删除或不属于当前身份，请从农药库重新选择。",
        );
        return;
      }
      const input = document.querySelector("#messageInput");
      if (!input || input.value.trim()) return;
      input.value = `请核对我农药库里的“${m.name}”这瓶药。${m.number ? `我填写的登记证号是 ${m.number}。` : "登记证号还没有填写。"}请核对已有资料，只追问缺少的用途或防治对象。`;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } catch {
      FarmerUI.toast("暂时无法读取所选农药，请从农药库重新打开。");
    }
  });
})();
