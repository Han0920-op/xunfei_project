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
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            r = MagicMock(status_code=200)
            r.__enter__.return_value = r
            if "vision.example" in url:
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
                n = sum("api.deepseek.com" in c[0] for c in calls)
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
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="text-test",
            VISION_PROVIDER="deepseek",
            DEEPSEEK_VISION_BASE_URL="https://vision.example/v1",
            DEEPSEEK_VISION_API_KEY="vision-test",
        ), patch.object(llm.requests, "post", side_effect=post), patch.object(
            dialogue.tools.TOOLS["search_web"], "func", return_value=json.dumps(result)
        ):
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
            self.assertEqual(len(calls), 3)
            self.assertEqual(
                calls[0][1]["headers"]["Authorization"], "Bearer vision-test"
            )
            self.assertEqual(
                calls[1][1]["headers"]["Authorization"], "Bearer text-test"
            )
            self.assertIn("可见麦穗局部发白", str(calls[1][1]["json"]["messages"]))
            self.page.reload()
            expect(
                card.get_by_role("link", name="小麦观察资料", exact=True)
            ).to_be_visible()
            self.context.route(
                "https://www.moa.gov.cn/test-zhimai",
                lambda route: route.fulfill(
                    body='<meta charset="utf-8"><h1>测试原文</h1>', content_type="text/html; charset=utf-8"
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
