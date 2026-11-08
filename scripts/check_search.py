"""Read-only search self-check, without model calls, keys or private case text."""

import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back_end"))
import knowledge
import web_search


def main():
    query = "小麦 赤霉病 麦穗局部发白 农业农村部"
    print("正在检查本地知识库和真实联网检索，不调用模型，不输出密钥…", flush=True)
    local = knowledge.search(query)
    began = time.monotonic()
    web = web_search.search_web(query)
    report = {
        "local_knowledge": {"status": local["status"], "count": len(local["results"])},
        "web_search": {
            k: web.get(k) for k in ("status", "query", "source", "message", "attempts")
        },
        "elapsed_seconds": round(time.monotonic() - began, 2),
    }
    report["web_search"]["results"] = [
        {k: row.get(k) for k in ("title", "url", "published_on", "retrieved_at")}
        for row in web.get("results", [])
    ]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if web.get("results") and local["status"] == "found" else 1


if __name__ == "__main__":
    raise SystemExit(main())
