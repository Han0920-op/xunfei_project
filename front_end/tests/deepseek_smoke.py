"""Configured DeepSeek text + hosted VL2 + visible pages; mocked provider transport."""

import json, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from playwright.sync_api import expect
import casework_smoke as helper
import config, dialogue, llm
from test_answer_review import checked


class DeepSeekBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def test_photo_decision_search_answer_and_open_source(self):
        self.check_photo_chain()

    def test_qwen_photo_tool_and_answer_retry_without_repeating_tool(self):
        self.check_photo_chain(qwen=True)

    def check_photo_chain(self, qwen=False):
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            r = MagicMock(status_code=200)
            r.__enter__.return_value = r
            if "vision.example" in url or kwargs["json"]["model"] == "qwen-vl-plus":
                r.iter_content.return_value = [
                    json.dumps(
                        {
                            "choices": [
                                {
                                    "finish_reason": "stop",
                                    "message": {
                                        "content": "可见麦穗局部发白，原因待核实"
                                    },
                                }
                            ]
                        }
                    ).encode()
                ]
            else:
                n = sum(bool(c[1]["json"].get("stream")) for c in calls)
                if qwen and n == 2:
                    r.status_code = 503
                    r.headers = {}
                    return r
                content = (
                    json.dumps(
                        {
                            "action": "tool",
                            "tool": "search_web",
                            "args": {"query": "小麦麦穗发白"},
                        }
                    )
                    if n == 1
                    else checked("需要结合症状和实际田间情况继续排查。")
                )
                r.iter_lines.return_value = [
                    (
                        "data: "
                        + json.dumps({"choices": [{"delta": {"content": content}}]})
                    ).encode(),
                    b"data: [DONE]",
                ]
            return r

        result = {
            "status": "ok",
            "query": "小麦麦穗发白",
            "results": [
                {
                    "title": "小麦观察资料",
                    "url": "https://www.moa.gov.cn/test-zhimai",
                    "published_on": "2026-04-20",
                    "summary": "请结合实际田间情况观察。",
                }
            ],
        }
        with patch.multiple(
            config,
            LLM_PROVIDER="qwen" if qwen else "deepseek",
            DASHSCOPE_API_KEY="qwen-test",
            QWEN_MODEL="qwen-plus",
            QWEN_VISION_MODEL="qwen-vl-plus",
            MODEL_CONNECT_RETRIES=1,
            DEEPSEEK_API_KEY="text-test",
            VISION_PROVIDER="qwen" if qwen else "deepseek",
            DEEPSEEK_VISION_BASE_URL="https://vision.example/v1",
            DEEPSEEK_VISION_API_KEY="vision-test",
        ), patch.object(llm.requests, "post", side_effect=post), patch.object(
            dialogue.tools.TOOLS["search_web"], "func", return_value=json.dumps(result)
        ) as search:
            self.page.goto(self.base + "/index.html")
            self.page.locator("#photoInput").set_input_files(
                str(Path(__file__).resolve().parents[1] / "assets/wheat-green.jpg")
            )
            expect(self.page.locator(".attachment")).to_be_visible()
            self.page.locator("#messageInput").fill("这片小麦穗部发白，请查询相关资料")
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer")).to_contain_text("继续排查")
            card = self.page.get_by_role("region", name="联网搜索相关网页")
            expect(
                card.get_by_role("link", name="小麦观察资料", exact=True)
            ).to_be_visible()
            expect(card).to_contain_text("2026-04-20")
            self.overflow()
            self.assertEqual(len(calls), 4 if qwen else 3)
            search.assert_called_once()
            self.assertEqual(
                calls[0][1]["headers"]["Authorization"],
                "Bearer qwen-test" if qwen else "Bearer vision-test",
            )
            self.assertEqual(
                calls[1][1]["headers"]["Authorization"],
                "Bearer qwen-test" if qwen else "Bearer text-test",
            )
            self.assertIn("可见麦穗局部发白", str(calls[1][1]["json"]["messages"]))
            self.page.reload()
            expect(
                card.get_by_role("link", name="小麦观察资料", exact=True)
            ).to_be_visible()
            self.context.route(
                "https://www.moa.gov.cn/test-zhimai",
                lambda route: route.fulfill(
                    body='<meta charset="utf-8"><h1>测试原文</h1>',
                    content_type="text/html; charset=utf-8",
                ),
            )
            with self.page.expect_popup() as popup:
                card.get_by_role("link", name="小麦观察资料", exact=True).click()
            expect(popup.value.get_by_role("heading", name="测试原文")).to_be_visible()
            self.assertTrue(self.page.url.startswith(self.base))
            popup.value.close()

    def test_failed_search_shows_manual_links_without_fake_sources(self):
        call = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "小麦穗部发白"}}
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter([call])
        ), patch.object(
            dialogue.tools.TOOLS["search_web"],
            "func",
            return_value=json.dumps(
                {"status": "unavailable", "query": "小麦穗部发白", "results": []}
            ),
        ):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("查询小麦穗部发白")
            self.page.locator("#sendButton").click()
            card = self.page.get_by_role("region", name="联网搜索相关网页")
            expect(card).to_contain_text("尚未取得可用网页")
            expect(card.get_by_role("link", name="在必应搜索")).to_be_visible()
            expect(card.locator(".web-source-card")).to_have_count(0)
            self.overflow()

    def test_untrusted_source_markup_and_local_urls_are_not_executable(self):
        self.page.goto(self.base + "/index.html")
        self.page.wait_for_function("!!window.SearchUI")
        self.page.evaluate(
            """() => { const section=document.createElement('div'); section.innerHTML=SearchUI.sources({results:[{title:'<img src=x onerror=alert(1)>',url:'https://www.moa.gov.cn/example',summary:'<script>alert(1)</script>'},{title:'unsafe',url:'javascript:alert(1)'},{title:'private',url:'http://192.168.1.1/'}]}); document.querySelector('#main').prepend(section); }"""
        )
        card = self.page.get_by_role("region", name="联网搜索相关网页")
        expect(card.locator(".web-source-card")).to_have_count(1)
        expect(card.locator("img,script")).to_have_count(0)
        expect(card).to_contain_text("<script>alert(1)</script>")

    def test_official_fallback_under_windows_encoding_reaches_source_cards(self):
        import web_search

        original = Path.read_text

        def gbk(path, encoding=None, errors=None):
            return original(path, encoding=encoding or "gbk", errors=errors)

        def get(url, **kwargs):
            response = MagicMock(status_code=200, headers={})
            response.__enter__.return_value = response
            response.iter_content.return_value = [
                (
                    '<meta name="ArticleTitle" content="小麦赤霉病官方资料"><meta name="PubDate" content="2026-04-20"><div class="TRS_Editor">小麦赤霉病历史资料，需要核实现场情况。</div>'.encode()
                    if "moa.gov.cn" in url
                    else b"<rss><channel></channel></rss>"
                )
            ]
            return response

        call = json.dumps(
            {
                "action": "tool",
                "tool": "search_web",
                "args": {"query": "小麦 赤霉病 麦穗发白 农业农村部"},
            }
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            Path, "read_text", gbk
        ), patch.object(web_search.requests, "get", side_effect=get), patch.object(
            dialogue.llm,
            "chat_stream",
            side_effect=[
                iter([call]),
                iter(["已找到相关历史官方资料，仍需核实现场症状。"]),
            ],
        ):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("请联网查询小麦赤霉病权威资料")
            self.page.locator("#sendButton").click()
            card = self.page.get_by_role("region", name="联网搜索相关网页")
            expect(self.page.locator(".agent-answer")).to_contain_text("已找到")
            expect(
                card.get_by_role("link", name="小麦赤霉病官方资料", exact=True).first
            ).to_be_visible()
            expect(card).to_contain_text("2026-04-20")
            expect(card).to_contain_text("实时读取的历史官方文章")
            self.page.reload()
            expect(
                card.get_by_role("link", name="小麦赤霉病官方资料", exact=True).first
            ).to_be_visible()
            self.overflow()

    def test_failed_search_keeps_specific_network_reason_in_saved_answer(self):
        import web_search, requests

        call = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "小麦 赤霉病"}}
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            web_search.requests,
            "get",
            side_effect=requests.exceptions.ProxyError("private-password"),
        ), patch.object(dialogue.llm, "chat_stream", return_value=iter([call])):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("请联网查小麦赤霉病")
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer")).to_contain_text("代理连接失败")
            card = self.page.get_by_role("region", name="联网搜索相关网页")
            expect(card.locator(".web-source-card")).to_have_count(0)
            expect(card).to_contain_text("不代表网上没有相关资料")
            self.page.reload()
            expect(self.page.locator(".agent-answer")).to_contain_text("代理连接失败")
            expect(self.page.locator("body")).not_to_contain_text("private-password")
