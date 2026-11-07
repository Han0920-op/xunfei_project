"""Real, bounded public web search. Results are leads, not reviewed prescriptions."""

import ipaddress
import re
import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import requests


def safe_url(value):
    try:
        u = urlsplit(value)
        if (
            u.scheme not in ("http", "https")
            or not u.hostname
            or u.username
            or u.password
            or u.port not in (None, 80, 443)
        ):
            return None
        if any(ord(c) < 33 for c in value) or len(value) > 2000:
            return None
        host = u.hostname.lower()
        if (
            host == "localhost"
            or "." not in host
            or host.endswith((".local", ".internal"))
        ):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value
    except (ValueError, TypeError):
        return None


def _public_search(query):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        return {"status": "unavailable", "message": "请缩短搜索关键词。", "results": []}
    try:
        began = time.monotonic()
        with requests.get(
            "https://www.bing.com/search",
            params={"q": query.strip(), "format": "rss", "setlang": "zh-cn"},
            timeout=(5, 10),
            stream=True,
            allow_redirects=False,
        ) as r:
            if r.status_code != 200:
                raise ValueError()
            chunks = []
            size = 0
            for chunk in r.iter_content(16384):
                size += len(chunk)
                if size > 1000000 or time.monotonic() - began > 15:
                    raise ValueError()
                chunks.append(chunk)
        body = b"".join(chunks)
        if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
            raise ValueError()
        root = ET.fromstring(body)
        if root.tag != "rss":
            raise ValueError()
        results = []
        seen = set()
        for row in root.findall("./channel/item"):
            url = safe_url(row.findtext("link", ""))
            if not url or url in seen:
                continue
            text = (
                row.findtext("title", "") + " " + row.findtext("description", "")
            ).lower()
            terms = [
                w
                for w in (
                    "小麦",
                    "赤霉病",
                    "锈病",
                    "白粉病",
                    "农药",
                    "wheat",
                    "fusarium",
                    "rust",
                    "mildew",
                )
                if w in query.lower()
            ]
            site = re.search(r"site:([a-zA-Z0-9.-]+)", query)
            specific = [w for w in terms if w not in ("小麦", "wheat")]
            if (specific or terms) and not any(w in text for w in (specific or terms)):
                continue
            if site and not (
                urlsplit(url).hostname == site[1]
                or urlsplit(url).hostname.endswith("." + site[1])
            ):
                continue
            seen.add(url)
            clean = lambda s: re.sub("<[^>]+>", "", s or "").strip()
            results.append(
                {
                    "title": clean(row.findtext("title"))[:200],
                    "url": url,
                    "domain": urlsplit(url).hostname,
                    "summary": clean(row.findtext("description"))[:800],
                }
            )
            if len(results) == 5:
                break
        return {
            "status": "ok",
            "results": results,
            "message": f"本次检索返回{len(results)}个网页。搜索摘要未经农技审校，不能证明登记状态或直接作为施药处方。",
            "source": "Bing公开网页检索",
        }
    except Exception:
        return {
            "status": "unavailable",
            "results": [],
            "message": "联网搜索失败或超时，未取得可用来源，请重试。",
        }


def _search_web(query):
    result = _public_search(query)
    if (
        result.get("results")
        or not isinstance(query, str)
        or not 1 <= len(query) <= 200
    ):
        return result
    # Public search can be empty. Read only the existing fixed official seed
    # pages afresh; never present these historical articles as current warnings.
    terms = [t for t in ("赤霉病", "锈病", "白粉病", "小麦") if t in query]
    if not terms:
        return result
    import json
    from pathlib import Path
    from agri_sources import Page

    rows = []
    urls = json.loads(
        (Path(__file__).parent / "data/knowledge/official_feeds.json").read_text()
    )["seed_urls"][:2]
    for url in urls:
        try:
            from agri_sources import safe_url as official_url

            official_url(url)
            started = time.monotonic()
            with requests.get(
                url, timeout=(3, 5), stream=True, allow_redirects=False
            ) as response:
                if response.status_code != 200:
                    continue
                data = []
                size = 0
                for chunk in response.iter_content(16384):
                    size += len(chunk)
                    if size > 1000000 or time.monotonic() - started > 8:
                        raise ValueError()
                    data.append(chunk)
            page = Page()
            page.feed(b"".join(data).decode("utf-8-sig"))
            title = page.meta.get("articletitle", "")
            date = (page.meta.get("pubdate") or page.meta.get("publishdate") or "")[:10]
            body = "".join(page.parts)
            if (
                not title
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
                or terms[0] not in title + body
            ):
                continue
            index = body.find(terms[0])
            quote = body[max(0, index - 40) : max(0, index - 40) + 500]
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "domain": urlsplit(url).hostname,
                    "published_on": date,
                    "summary": quote,
                    "notice": "实时读取的历史官方文章，适用性待核对，不是当前预警或施药许可。",
                }
            )
        except Exception:
            continue
    if rows:
        return {
            "status": "ok",
            "results": rows,
            "source": "已配置官方页面实时补充检索",
            "message": "公开搜索未取得相关网页；已实时读取配置中的官方历史文章。发布日期与适用条件须另行核对，不代表全网搜索覆盖或当前预警。",
        }
    return result


def search_web(query):
    # Preserve the actual public query for source cards and explicit manual fallback.
    public_query = query.strip() if isinstance(query, str) else ""
    if any(term in public_query for term in ("麦穗", "麦苗", "麦叶")) and "小麦" not in public_query:
        public_query = "小麦 " + public_query
    result = _search_web(public_query)
    return {**result, "query": public_query[:200]}
