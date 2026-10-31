(() => {
  window.PersonalReady ||= fetch("/api/personal/session");
  document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(location.search);
    if (params.has("medicine")) {
      const input = document.querySelector("#messageInput");
      if (input) {
        input.value = "请读取我的农药库，帮我核对手里的药。";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  });
})();
