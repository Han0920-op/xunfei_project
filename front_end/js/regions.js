/* Subscription reference context stays distinct from the actual photo location. */
(() => {
  let items = [],
    state = "loading";
  const { esc, icon } = FarmerUI;
  async function refresh() {
    try {
      await window.PersonalReady;
      const r = await fetch("/api/intelligence/chat-context", {
        cache: "no-store",
      });
      if (!r.ok) throw Error();
      const data = await r.json();
      if (!Array.isArray(data.options)) throw Error();
      items = data.options;
      state = "ready";
    } catch {
      state = "unavailable";
    }
  }
  const ready = refresh();
  function markup(value = "", disabled = false) {
    if (state === "loading")
      return '<p class="chat-region-note">正在读取地区订阅…</p>';
    if (state === "unavailable")
      return '<p class="chat-region-note">地区订阅暂时无法读取，可直接说明本次地区。</p>';
    const defaultLabel =
      items.length === 1
        ? "按订阅参考：" + items[0].province + " " + items[0].city
        : items.length
          ? "请选择本次参考地区"
          : "尚未订阅地区";
    const stale =
      value && value !== "none" && !items.some((s) => s.id === value);
    return `<div class="chat-region"><label>${icon("leaf")}本次参考地区<select id="chatRegion" aria-label="本次参考地区" ${disabled ? "disabled" : ""}><option value="" ${!value ? "selected" : ""}>${esc(defaultLabel)}</option><option value="none" ${value === "none" ? "selected" : ""}>不使用订阅地区</option>${stale ? `<option value="${esc(value)}" selected disabled>此前地区订阅不可用，请重新选择</option>` : ""}${items.map((s) => `<option value="${esc(s.id)}" ${value === s.id ? "selected" : ""}>${esc(s.province)} ${esc(s.city)}</option>`).join("")}</select></label><a href="intelligence.html">管理地区订阅</a><small>仅作回答参考；照片实际地点以你本次说明为准。</small></div>`;
  }
  function evidence(data) {
    if (!data?.selected) return "";
    const s = data.selected;
    return `<div class="knowledge-quote"><strong>本次参考地区 · ${esc(s.province)} ${esc(s.city)}</strong><p>来自你选择的地区订阅，未作为照片拍摄地或现场发病事实保存。</p>${(data.official_signals || []).map((b) => `<p>相关公开情报：${esc(b.title)} · 发布 ${esc(b.published_on)} · 范围 ${esc(b.regions.join("、"))}${b.cities?.length ? " " + esc(b.cities.join("、")) : "（省级）"}</p>`).join("") || "<small>本次未取得符合地区、对象和有效期要求的病虫情报。</small>"}</div>`;
  }
  window.RegionalChat = { ready, refresh, markup, evidence };
})();
