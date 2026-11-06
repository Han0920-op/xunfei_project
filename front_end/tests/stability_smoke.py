import json, unittest
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import dialogue, config, memory
from test_answer_review import checked


class StabilityBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown

    def test_search_failure_finishes_and_does_not_leave_spinner(self):
        call = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "赤霉病"}}
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter([call])
        ) as model, patch.object(
            dialogue.tools.TOOLS["search_web"],
            "func",
            return_value='{"status":"unavailable","results":[],"message":"搜索暂时不可用"}',
        ):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("帮我联网搜索一下")
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer")).to_contain_text(
                "未能取得可用资料"
            )
            expect(self.page.locator(".thinking")).to_have_count(0)
            expect(self.page.locator("#sendButton")).to_be_enabled()
            self.assertEqual(model.call_count, 1)
            self.page.reload()
            expect(self.page.locator(".agent-answer")).to_contain_text(
                "未能取得可用资料"
            )

    def test_old_image_context_format_retry_replaces_preview(self):
        memory.save_turn(
            self.who,
            "photo-case",
            "photo-first",
            "看一下照片",
            "请补拍穗轴",
            [{"status": "ok", "content": "穗部局部发白"}],
            [],
            True,
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm,
            "chat_stream",
            side_effect=[
                iter(["未检查的错误正文"]),
                iter([checked("目前仍需进一步观察。")]),
            ],
        ):
            self.page.goto(self.base + "/index.html?case=photo-case")
            self.page.locator("#messageInput").fill("继续分析")
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer").last).to_have_text(
                "目前仍需进一步观察。"
            )
            expect(self.page.locator("body")).not_to_contain_text("未检查的错误正文")
            expect(self.page.locator(".thinking")).to_have_count(0)

    def test_manual_retry_reuses_case_and_turn_identifiers(self):
        requests = []

        def capture(route):
            requests.append(route.request.post_data)
            route.continue_()

        self.page.route("**/api/agent/chat", capture)
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm,
            "chat_stream",
            side_effect=[RuntimeError("failure"), iter(["请描述主要症状。"])],
        ):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("帮我看一下")
            self.page.locator("#sendButton").click()
            expect(self.page.locator("#sendError")).not_to_be_empty()
            self.page.get_by_role("button", name="重新发送", exact=True).click()
            expect(self.page.locator(".agent-answer")).to_contain_text("请描述主要症状")
        import re

        def field(body, key):
            return re.search('name="' + key + '"\\r\\n\\r\\n([^\\r]+)', body)[1]

        self.assertEqual(field(requests[0], "case_id"), field(requests[1], "case_id"))
        self.assertEqual(field(requests[0], "turn_id"), field(requests[1], "turn_id"))
