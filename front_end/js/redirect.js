(() => {
  const page = location.pathname.split("/").pop(),
    p = new URLSearchParams(location.search);
  let target = "index.html";
  const record = p.get("record"),
    clinical =
      p.get("clinicalId") || (page === "case.html" ? p.get("id") : null);
  if (record) target += "?record=" + encodeURIComponent(record);
  else if (clinical)
    target += "?record=" + encodeURIComponent("legacy-" + clinical);
  else if (page === "medication.html") target += "?intent=medicine";
  else if (
    [
      "case.html",
      "tasks.html",
      "fields.html",
      "field.html",
      "compare.html",
    ].includes(page) ||
    p.has("caseId") ||
    p.has("conversationId")
  )
    target = "history.html";
  location.replace(target);
})();
