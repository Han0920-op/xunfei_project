/* Local records and photos. Existing v1 data is retained, never reset. */
(() => {
  "use strict";
  const KEY = "zhimai.frontend.v1";
  let state = {},
    readError = "";
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("invalid");
      state = parsed;
    }
  } catch {
    readError =
      "暂时读不到本机的旧记录。为保护原有资料，当前不会覆盖保存，请先检查浏览器存储。";
  }
  const id = () =>
    crypto.randomUUID?.() ||
    `zm-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const date = () =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  function write(fn) {
    if (readError) throw new Error(readError);
    const next = structuredClone(state);
    fn(next);
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      throw new Error(
        "没有保存成功。输入和照片仍保留在这里，请检查设备存储空间后重试。",
      );
    }
    state = next;
  }
  const safeSrc = (s) =>
    /^(assets\/[\w./-]+|data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+)$/.test(
      s || "",
    )
      ? s
      : "";
  function legacy(c) {
    const photos = [];
    if (safeSrc(c.image))
      photos.push({
        id: `old-${c.id}`,
        legacyCaseId: c.id,
        date: c.capturedAt || c.createdAt,
        name: "此前照片",
      });
    for (const f of c.followups || [])
      if (safeSrc(f.image))
        photos.push({
          id: `old-${f.id}`,
          legacyCaseId: c.id,
          legacyFollowupId: f.id,
          date: f.date,
          name: "复查照片",
        });
    return {
      id: `legacy-${c.id}`,
      legacyId: c.id,
      title: c.title || "此前的问题",
      kind: "disease",
      step: "result",
      createdAt: c.createdAt || "",
      updatedAt: c.events?.at(-1)?.at || c.createdAt || "",
      archived: Boolean(c.archived),
      demo: Boolean(c.demo),
      source: "legacy",
      facts: {
        description: c.symptoms || "",
        stage: c.stage || "不清楚",
        distribution: c.distribution || "还没看清",
      },
      photos,
      messages: [
        {
          id: `old-msg-${c.id}`,
          role: "user",
          text: c.symptoms || c.title || "此前的现场记录",
          photoId: photos[0]?.id,
        },
        {
          id: `old-result-${c.id}`,
          role: "assistant",
          type: "legacy",
          text: "这是以前保存的问题。可以带着新照片回来复查。",
          oldId: c.id,
        },
      ],
      actions: c.actions || [],
      followups: c.followups || [],
      followupDate: c.followupDone ? "" : c.proposedDate || "",
    };
  }
  function records() {
    const current = state.farmerThreads || [];
    const currentIds = new Set(current.map((x) => x.id));
    const hidden = new Set(state.farmerHiddenLegacy || []);
    return [
      ...current,
      ...(state.clinicalCases || [])
        .filter(
          (c) =>
            !currentIds.has(`legacy-${c.id}`) && !hidden.has(`legacy-${c.id}`),
        )
        .map(legacy),
    ].sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
  }
  function get(recordId) {
    return records().find((x) => x.id === recordId);
  }
  function save(record) {
    write((s) => {
      s.farmerThreads ??= [];
      const index = s.farmerThreads.findIndex((x) => x.id === record.id);
      if (index < 0) s.farmerThreads.push(record);
      else s.farmerThreads[index] = record;
    });
  }
  function remove(recordId) {
    const r = get(recordId);
    write((s) => {
      s.farmerThreads = (s.farmerThreads || []).filter(
        (x) => x.id !== recordId,
      );
      if (recordId.startsWith("legacy-")) {
        s.farmerHiddenLegacy ??= [];
        if (!s.farmerHiddenLegacy.includes(recordId))
          s.farmerHiddenLegacy.push(recordId);
      }
    });
    for (const p of r?.photos || [])
      if (!p.url && !p.legacyCaseId) deletePhoto(p.id).catch(() => {});
  }
  function oldDetail(oldId) {
    return structuredClone(
      (state.clinicalCases || []).find((c) => c.id === oldId) || null,
    );
  }
  let dbPromise;
  const urls = new Map();
  function db() {
    if (!dbPromise)
      dbPromise = new Promise((resolve, reject) => {
        if (!window.indexedDB) {
          reject(
            new Error("当前浏览器无法保存照片，请移除照片后先用文字描述。"),
          );
          return;
        }
        const req = indexedDB.open("zhimai.farmer.photos", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("photos");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => {
          dbPromise = null;
          reject(new Error("照片未能保存，请检查浏览器存储设置。"));
        };
        req.onblocked = () =>
          reject(new Error("请关闭其他智麦页面后重试保存照片。"));
      });
    return dbPromise;
  }
  async function putPhoto(file) {
    const database = await db();
    const photo = {
      id: id(),
      name: file.name,
      type: file.type,
      size: file.size,
      date: date(),
    };
    await new Promise((resolve, reject) => {
      const tx = database.transaction("photos", "readwrite");
      tx.objectStore("photos").put(file, photo.id);
      tx.oncomplete = resolve;
      tx.onabort = tx.onerror = () =>
        reject(new Error("照片没有保存成功，请检查设备存储空间后重试。"));
    });
    return photo;
  }
  async function photoUrl(photo) {
    if (photo.legacyCaseId) {
      const c = (state.clinicalCases || []).find(
        (c) => c.id === photo.legacyCaseId,
      );
      const src = photo.legacyFollowupId
        ? (c?.followups || []).find((f) => f.id === photo.legacyFollowupId)
            ?.image
        : c?.image;
      if (!safeSrc(src)) throw new Error("此前照片不可用");
      return src;
    }
    if (photo.url) return safeSrc(photo.url);
    if (urls.has(photo.id)) return urls.get(photo.id);
    const database = await db();
    const blob = await new Promise((resolve, reject) => {
      const req = database
        .transaction("photos")
        .objectStore("photos")
        .get(photo.id);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(new Error("照片读取失败"));
    });
    if (!blob) throw new Error("这张照片未保存在当前设备上");
    // A photo can appear both in a message and in a comparison card.
    if (urls.has(photo.id)) return urls.get(photo.id);
    const url = URL.createObjectURL(blob);
    urls.set(photo.id, url);
    return url;
  }
  async function deletePhoto(photoId) {
    const database = await db();
    await new Promise((resolve, reject) => {
      const tx = database.transaction("photos", "readwrite");
      tx.objectStore("photos").delete(photoId);
      tx.oncomplete = resolve;
      tx.onabort = tx.onerror = reject;
    });
    if (urls.has(photoId)) {
      URL.revokeObjectURL(urls.get(photoId));
      urls.delete(photoId);
    }
  }
  window.addEventListener("pagehide", () => {
    for (const url of urls.values()) URL.revokeObjectURL(url);
    urls.clear();
  });
  window.FarmerStore = {
    id,
    date,
    get,
    records,
    save,
    remove,
    oldDetail,
    putPhoto,
    photoUrl,
    deletePhoto,
    get readError() {
      return readError;
    },
  };
})();
