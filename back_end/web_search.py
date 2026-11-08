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


# Keep external failures separate from "no matching results". Never include
# exception strings, proxy credentials, or remote error bodies in tool output.
class SearchFailure(ValueError):
    def __init__(self, reason, http_status=None):
        super().__init__(reason)
        self.reason, self.http_status = reason, http_status


def _failure(exc):
    if isinstance(exc, SearchFailure):
        return {
            "reason": exc.reason,
            **({"http_status": exc.http_status} if exc.http_status else {}),
        }
    if isinstance(exc, requests.exceptions.ProxyError):
        return {"reason": "proxy_failed"}
    if isinstance(exc, requests.exceptions.SSLError):
        return {"reason": "tls_failed"}
    if isinstance(exc, requests.Timeout):
        return {"reason": "timeout"}
    if isinstance(exc, requests.RequestException):
        return {"reason": "connection_failed"}
    return {"reason": "invalid_response"}


def _read(url, *, params=None, deadline=None, official=False):
    from urllib.parse import urljoin
    from agri_sources import safe_url as official_url

    deadline = deadline or time.monotonic() + 12
    for _ in range(3):
        if official:
            official_url(url)
        elif (
            urlsplit(url).hostname not in ("www.bing.com", "cn.bing.com", "bing.com")
            or urlsplit(url).scheme != "https"
            or not safe_url(url)
        ):
            raise SearchFailure("unsafe_redirect")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SearchFailure("timeout")
        with requests.get(
            url,
            params=params,
            timeout=(min(3, remaining), min(6, remaining)),
            stream=True,
            allow_redirects=False,
            headers={
                "User-Agent": "Zhimai-SourceReader/1.1",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        ) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                params = None
                continue
            if response.status_code != 200:
                raise SearchFailure("http_error", response.status_code)
            parts, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 1000000:
                    raise SearchFailure("response_too_large")
                if time.monotonic() > deadline:
                    raise SearchFailure("timeout")
                parts.append(chunk)
            return url, b"".join(parts)
    raise SearchFailure("redirect_limit")


def _matches(query, text, url):
    terms = [
        word
        for word in (
            "赤霉病",
            "条锈病",
            "锈病",
            "白粉病",
            "纹枯病",
            "茎基腐病",
            "农药",
            "fusarium",
            "rust",
            "mildew",
        )
        if word in query.lower()
    ]
    crop = [word for word in ("小麦", "wheat") if word in query.lower()]
    if terms and not any(word in text.lower() for word in terms):
        return False
    if crop and not any(word in text.lower() for word in crop):
        return False
    site = re.search(r"site:([a-zA-Z0-9.-]+)", query, re.I)
    host = urlsplit(url).hostname or ""
    return not site or host == site[1].lower() or host.endswith("." + site[1].lower())


def _public_search(query, *, endpoint="https://www.bing.com/search", deadline=None):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        return {
            "status": "unavailable",
            "reason": "invalid_query",
            "message": "请缩短搜索关键词。",
            "results": [],
        }
    try:
        _, body = _read(
            endpoint,
            params={"q": query.strip(), "format": "rss", "setlang": "zh-cn"},
            deadline=deadline,
        )
        if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
            raise SearchFailure("unexpected_format")
        root = ET.fromstring(body)
        if root.tag != "rss":
            raise SearchFailure("unexpected_format")
        results, seen = [], set()
        from email.utils import parsedate_to_datetime

        for row in root.findall("./channel/item"):
            url = safe_url(row.findtext("link", ""))
            text = row.findtext("title", "") + " " + row.findtext("description", "")
            if not url or url in seen or not _matches(query, text, url):
                continue
            seen.add(url)
            clean = lambda value: re.sub("<[^>]+>", "", value or "").strip()
            item = {
                "title": clean(row.findtext("title"))[:200],
                "url": url,
                "domain": urlsplit(url).hostname,
                "summary": clean(row.findtext("description"))[:800],
            }
            try:
                item["published_on"] = (
                    parsedate_to_datetime(row.findtext("pubDate", ""))
                    .date()
                    .isoformat()
                )
            except (ValueError, TypeError, OverflowError):
                pass  # Never invent a missing publication date.
            results.append(item)
            if len(results) == 5:
                break
        return {
            "status": "ok",
            "results": results,
            "reason": "found" if results else "no_match",
            "message": f"本次检索返回{len(results)}个网页。搜索摘要未经农技审校，不能证明登记状态或直接作为施药处方。",
            "source": "Bing公开网页检索",
        }
    except Exception as exc:
        return {"status": "unavailable", "results": [], **_failure(exc)}


REASONS = {
    "no_match": "未匹配到相关网页",
    "timeout": "请求超时",
    "proxy_failed": "代理连接失败",
    "tls_failed": "证书校验失败",
    "connection_failed": "网络连接失败",
    "http_error": "网站返回错误状态",
    "unexpected_format": "网站没有返回搜索结果格式",
    "invalid_response": "网页格式未能解析",
    "config_unavailable": "官方来源配置无法读取",
    "unsafe_redirect": "跳转地址不受支持",
    "redirect_limit": "网页重定向过多",
    "response_too_large": "网页超过读取大小限制",
    "invalid_query": "查询词无效",
}


def _official_search(query, deadline):
    import json
    from pathlib import Path
    from datetime import date, datetime, timezone
    from agri_sources import Page, safe_url as official_url

    attempts, rows = [], []
    try:
        # Explicit encoding matters on Windows, whose default may be GBK.
        document = json.loads(
            (Path(__file__).parent / "data/knowledge/official_feeds.json").read_text(
                encoding="utf-8-sig"
            )
        )
        urls = document["seed_urls"]
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise ValueError()
        urls = urls[:2]
    except (OSError, ValueError, KeyError, TypeError):
        return [], [{"source": "官方网页", "reason": "config_unavailable"}]
    for url in urls:
        try:
            official_url(url)
            actual_url, body = _read(
                url, official=True, deadline=min(deadline, time.monotonic() + 8)
            )
            page = Page()
            page.feed(body.decode("utf-8-sig"))
            title = page.meta.get("articletitle", "")
            published = (
                page.meta.get("pubdate") or page.meta.get("publishdate") or ""
            )[:10]
            body = "".join(page.parts)
            if not title or not body.strip():
                raise SearchFailure("invalid_response")
            date.fromisoformat(published)
            if not _matches(query, title + body, actual_url):
                attempts.append({"source": "官方网页", "reason": "no_match"})
                continue
            terms = [
                t
                for t in ("赤霉病", "锈病", "白粉病", "纹枯病", "茎基腐病", "小麦")
                if t in query
            ]
            index = next((body.find(t) for t in terms if t in body), 0)
            quote = body[max(0, index - 40) : max(0, index - 40) + 500]
            rows.append(
                {
                    "title": title,
                    "url": actual_url,
                    "domain": urlsplit(actual_url).hostname,
                    "published_on": published,
                    "summary": quote,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "notice": "实时读取的历史官方文章，适用性待核对，不是当前预警或施药许可。",
                }
            )
            attempts.append({"source": "官方网页", "reason": "found"})
        except Exception as exc:
            attempts.append({"source": "官方网页", **_failure(exc)})
    return rows, attempts


def _search_web(query):
    deadline = time.monotonic() + 30
    result = _public_search(query)
    attempts = [
        {
            "source": "必应检索",
            "reason": result.get(
                "reason", "found" if result.get("results") else "no_match"
            ),
        }
    ]
    if result.get("http_status"):
        attempts[0]["http_status"] = result["http_status"]
    if (
        result.get("results")
        or not isinstance(query, str)
        or not 1 <= len(query) <= 200
    ):
        return {**result, "attempts": attempts}
    if any(
        term in query
        for term in ("小麦", "赤霉病", "锈病", "白粉病", "纹枯病", "茎基腐病")
    ):
        rows, official_attempts = _official_search(query, deadline)
        attempts.extend(official_attempts)
        if rows:
            return {
                "status": "ok",
                "results": rows,
                "attempts": attempts,
                "source": "已配置官方页面实时补充检索",
                "message": "公开搜索未取得相关网页；已实时读取配置中的官方历史文章。发布日期与适用条件须另行核对，不代表全网搜索覆盖或当前预警。",
            }
    if time.monotonic() < deadline:
        regional = _public_search(
            query, endpoint="https://cn.bing.com/search", deadline=deadline
        )
        attempts.append(
            {
                "source": "必应备用入口",
                "reason": regional.get("reason", "no_match"),
                **(
                    {"http_status": regional["http_status"]}
                    if regional.get("http_status")
                    else {}
                ),
            }
        )
        if regional.get("results"):
            return {**regional, "attempts": attempts}
        if regional.get("status") == "ok":
            result = regional
    descriptions = list(
        dict.fromkeys(
            a["source"] + "：" + REASONS.get(a["reason"], "请求未完成")
            for a in attempts
        )
    )
    return {
        **result,
        "results": [],
        "attempts": attempts,
        "message": "未取得可用网页。"
        + "；".join(descriptions)
        + "。这不代表网上没有相关资料。",
    }


def search_web(query):
    public_query = query.strip() if isinstance(query, str) else ""
    if (
        any(term in public_query for term in ("麦穗", "麦苗", "麦叶"))
        and "小麦" not in public_query
    ):
        public_query = "小麦 " + public_query
    # Long natural-language requests must not disable all search routes.
    if len(public_query) > 200:
        keywords = [
            t
            for t in (
                "小麦",
                "赤霉病",
                "条锈病",
                "白粉病",
                "纹枯病",
                "茎基腐病",
                "麦穗",
                "发白",
                "粉红",
                "农药",
                "农业农村部",
            )
            if t in public_query
        ]
        site = re.search(r"site:[a-zA-Z0-9.-]+", public_query, re.I)
        public_query = (
            " ".join(keywords + ([site[0]] if site else []))
            if keywords
            else public_query[:200]
        )
    result = _search_web(public_query)
    return {**result, "query": public_query[:200]}
