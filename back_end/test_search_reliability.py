"""Windows encoding, official fallback and bounded public search regression."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import requests
import web_search as search
import knowledge

EMPTY = b"<rss><channel></channel></rss>"
ARTICLE = '<meta name="ArticleTitle" content="小麦赤霉病防控"><meta name="PubDate" content="2026-04-20"><div class="TRS_Editor">小麦赤霉病防控历史资料</div>'.encode()


def response(body=EMPTY, status=200, headers=None):
    r = MagicMock(status_code=status, headers=headers or {})
    r.__enter__.return_value = r
    r.iter_content.return_value = [body]
    return r


class SearchReliabilityTests(unittest.TestCase):
    def test_windows_gbk_default_still_reads_utf8_official_config(self):
        original = Path.read_text

        def gbk(path, encoding=None, errors=None):
            return original(path, encoding=encoding or "gbk", errors=errors)

        def get(url, **kwargs):
            return response(ARTICLE if "moa.gov.cn" in url else EMPTY)

        with patch.object(Path, "read_text", gbk), patch.object(
            search.requests, "get", side_effect=get
        ):
            result = search.search_web("小麦 赤霉病 麦穗局部发白 农业农村部")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"][0]["published_on"], "2026-04-20")
        self.assertIn("历史", result["results"][0]["notice"])
        self.assertTrue(result["results"][0]["retrieved_at"])

    def test_missing_config_does_not_abort_alternate_search(self):
        match = "<rss><channel><item><title>小麦赤霉病</title><link>https://www.moa.gov.cn/example</link></item></channel></rss>".encode()
        with patch.object(
            Path, "read_text", side_effect=FileNotFoundError("private-path")
        ), patch.object(
            search.requests, "get", side_effect=[response(), response(match)]
        ) as get:
            result = search.search_web("小麦赤霉病")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["results"]), 1)
        self.assertIn("config_unavailable", str(result["attempts"]))
        self.assertNotIn("private-path", str(result))
        self.assertEqual(get.call_args.args[0], "https://cn.bing.com/search")

    def test_failed_requests_have_safe_reasons_not_fake_empty_success(self):
        for exc, reason in [
            (requests.Timeout("private-url"), "timeout"),
            (requests.exceptions.ProxyError("private-password"), "proxy_failed"),
            (requests.exceptions.SSLError("private-cert"), "tls_failed"),
        ]:
            with patch.object(search.requests, "get", side_effect=exc):
                result = search.search_web("小麦赤霉病")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["results"], [])
            self.assertTrue(all(a["reason"] == reason for a in result["attempts"]))
            self.assertNotIn("private-", json.dumps(result))
            self.assertIn("不代表网上没有", result["message"])

    def test_no_match_is_distinct_from_transport_failure(self):
        with patch.object(search.requests, "get", return_value=response()):
            result = search.search_web("量子计算")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"], [])
        self.assertTrue(all(a["reason"] == "no_match" for a in result["attempts"]))

    def test_approved_redirect_followed_but_untrusted_redirect_never_requested(self):
        official = "https://www.moa.gov.cn/xw/zwdt/new.htm"
        with patch.object(
            search.requests,
            "get",
            side_effect=[
                response(status=302, headers={"Location": official}),
                response(ARTICLE),
            ],
        ) as get:
            url, body = search._read("https://www.moa.gov.cn/xw/old.htm", official=True)
        self.assertEqual(url, official)
        self.assertEqual(body, ARTICLE)
        self.assertEqual(get.call_count, 2)
        for destination in (
            "http://127.0.0.1/",
            "https://evil.example/private",
            "https://user:password@www.bing.com/search",
        ):
            with patch.object(
                search.requests,
                "get",
                return_value=response(status=302, headers={"Location": destination}),
            ) as get:
                result = search._public_search("小麦")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(get.call_count, 1)

    def test_official_fallback_respects_site_and_disease(self):
        with patch.object(search.requests, "get", return_value=response(ARTICLE)):
            for query in ("小麦白粉病", "小麦赤霉病 site:other.gov.cn"):
                rows, _ = search._official_search(query, time.monotonic() + 20)
                self.assertEqual(rows, [])
        self.assertFalse(
            search._matches(
                "小麦 赤霉病", "玉米 赤霉病", "https://www.moa.gov.cn/example"
            )
        )

    def test_long_query_reduced_without_adding_a_diagnosis(self):
        with patch.object(
            search, "_search_web", return_value={"status": "ok", "results": []}
        ) as call:
            result = search.search_web(
                "请联网查找相关资料。" * 40 + "小麦 麦穗 发白 site:moa.gov.cn"
            )
        self.assertLessEqual(len(call.call_args.args[0]), 200)
        self.assertIn("site:moa.gov.cn", result["query"])
        self.assertNotIn("赤霉病", result["query"])

    def test_budget_expired_and_oversized_response_are_bounded(self):
        with patch.object(search.requests, "get") as get:
            with self.assertRaises(search.SearchFailure):
                search._read(
                    "https://www.bing.com/search", deadline=time.monotonic() - 1
                )
            get.assert_not_called()
        with patch.object(
            search.requests, "get", return_value=response(b"x" * 1000001)
        ):
            result = search._public_search("小麦")
        self.assertEqual(result["reason"], "response_too_large")

    def test_windows_newlines_only_are_accepted_in_verified_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            for filename in ("observations.json", "source.txt"):
                Path(tmp, filename).write_bytes(
                    (knowledge.DATA_DIR / filename).read_bytes().replace(b"\n", b"\r\n")
                )
            result = knowledge.search("小麦赤霉病麦穗发白", directory=tmp)
            self.assertEqual(result["status"], "found")
            archive = Path(tmp, "source.txt")
            archive.write_bytes(archive.read_bytes() + b"changed")
            self.assertEqual(
                knowledge.search("小麦赤霉病", directory=tmp)["status"], "unavailable"
            )
