"""Real browser navigation with a live, delayed chat stream; no paid APIs."""

import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import config, dialogue, llm


class NavigationTests(unittest.TestCase):
    def setUp(self):
        helper.CaseworkBrowserTests.setUp(self)
        self.page.set_viewport_size({"width": 1440, "height": 1000})
        self.dialogs = []
        self.page.on("dialog", lambda d: (self.dialogs.append(d.type), d.dismiss()))

    tearDown = helper.CaseworkBrowserTests.tearDown

    def view(self):
        return self.page.frame_locator("iframe.app-navigation-view:not([hidden])")

    def test_draft_photo_switch_back_and_history_navigation(self):
        self.page.goto(self.base + "/index.html?intent=medicine")
        self.page.locator("#messageInput").fill("我手里有这瓶药，先帮我核对")
        self.page.locator("#photoInput").set_input_files(
            str(Path(__file__).resolve().parents[1] / "assets/wheat-green.jpg")
        )
        expect(self.page.locator(".attachment")).to_be_visible()
        self.page.get_by_role("link", name="我的农药库", exact=True).click()
        expect(
            self.view().get_by_role("button", name="新增农药", exact=True)
        ).to_be_visible()
        self.view().get_by_role("link", name="提醒", exact=True).click()
        expect(
            self.view().get_by_role("button", name="新增提醒", exact=True)
        ).to_be_visible()
        self.view().get_by_role("navigation", name="主导航").get_by_role(
            "link", name="问智麦", exact=True
        ).click()
        expect(self.page.locator("#messageInput")).to_have_value(
            "我手里有这瓶药，先帮我核对"
        )
        expect(self.page.locator(".attachment")).to_be_visible()
        self.page.go_back()
        expect(
            self.view().get_by_role("button", name="新增提醒", exact=True)
        ).to_be_visible()
        self.page.go_forward()
        expect(self.page.locator("#messageInput")).to_have_value(
            "我手里有这瓶药，先帮我核对"
        )
        self.assertEqual(self.dialogs, [])

    def test_stream_continues_away_without_stealing_url_and_followup_has_history(self):
        release = threading.Event()

        def answer(*args, **kwargs):
            if not release.wait(15):
                raise RuntimeError("test stream not released")
            yield "请观察叶背并补充异常分布。"

        try:
            with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
                dialogue.llm, "chat_stream", side_effect=answer
            ) as model:
                self.page.goto(self.base + "/index.html")
                self.page.locator("#messageInput").fill("小麦叶片发黄了")
                self.page.locator("#sendButton").click()
                expect(self.page.locator(".thinking")).to_be_visible()
                self.page.get_by_role("navigation", name="主导航").get_by_role(
                    "link", name="我的记录", exact=True
                ).click()
                expect(
                    self.view().get_by_role("link", name="问个新问题", exact=True)
                ).to_be_visible()
                release.set()
                self.page.wait_for_function(
                    "FarmerStore.records().some(r => r.messages?.some(m => m.text === '请观察叶背并补充异常分布。'))"
                )
                self.assertTrue(self.page.url.endswith("history.html"))
                self.view().get_by_role("navigation", name="主导航").get_by_role(
                    "link", name="问智麦", exact=True
                ).click()
                expect(self.page.locator(".agent-answer")).to_have_text(
                    "请观察叶背并补充异常分布。"
                )
                expect(self.page.locator("#sendButton")).to_be_enabled()
                self.assertEqual(model.call_count, 1)
                self.page.locator("#messageInput").fill("叶背没有虫子")
                self.page.locator("#sendButton").click()
                expect(self.page.locator(".agent-answer")).to_have_count(2)
                self.assertIn("小麦叶片发黄了", str(model.call_args.args[0]))
                self.assertEqual(model.call_count, 2)
                self.assertEqual(self.dialogs, [])
        finally:
            release.set()

    def test_error_while_away_preserves_input_and_retry(self):
        release = threading.Event()

        def fail(*args, **kwargs):
            release.wait(15)
            raise llm.LLMError("unavailable", "model_unavailable")
            yield

        try:
            with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
                dialogue.llm, "chat_stream", side_effect=fail
            ):
                self.page.goto(self.base + "/index.html")
                self.page.locator("#messageInput").fill("请帮我看看小麦")
                self.page.locator("#sendButton").click()
                expect(self.page.locator(".thinking")).to_be_visible()
                self.page.get_by_role("link", name="提醒", exact=True).click()
                expect(
                    self.view().get_by_role("button", name="新增提醒", exact=True)
                ).to_be_visible()
                release.set()
                self.page.wait_for_function(
                    "document.getElementById('sendError')?.textContent.length > 0"
                )
                self.view().get_by_role("navigation", name="主导航").get_by_role(
                    "link", name="问智麦", exact=True
                ).click()
                expect(self.page.locator("#messageInput")).to_have_value(
                    "请帮我看看小麦"
                )
            with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
                dialogue.llm, "chat_stream", return_value=iter(["请说明主要症状。"])
            ):
                self.page.get_by_role("button", name="重新发送", exact=True).click()
                expect(self.page.locator(".agent-answer")).to_have_text(
                    "请说明主要症状。"
                )
            self.assertEqual(self.dialogs, [])
        finally:
            release.set()

    def test_explicit_new_chat_and_old_record_keep_separate_drafts(self):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter(["请补拍叶背。"])
        ) as model:
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("旧问题叶片发黄")
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer")).to_be_visible()
            record = self.page.evaluate(
                "FarmerStore.records().find(r => r.messages?.some(m => m.text === '旧问题叶片发黄')).id"
            )
            self.page.locator("#messageInput").fill("旧问题尚未发送的补充")
            self.page.get_by_role("navigation", name="主导航").get_by_role(
                "link", name="我的记录", exact=True
            ).click()
            self.view().get_by_role("link", name="问个新问题", exact=True).click()
            expect(self.view().locator("#messageInput")).to_have_value("")
            self.view().locator("#messageInput").fill("新问题的草稿")
            self.view().get_by_role("link", name="我的农药库", exact=True).click()
            self.view().get_by_role("navigation", name="主导航").get_by_role(
                "link", name="问智麦", exact=True
            ).click()
            expect(self.view().locator("#messageInput")).to_have_value("新问题的草稿")
            self.view().get_by_role("link", name="我的记录", exact=True).click()
            self.view().locator(
                'a.record-main[href="index.html?record=' + record + '"]'
            ).click()
            expect(self.page.locator("#messageInput")).to_have_value(
                "旧问题尚未发送的补充"
            )
            self.assertEqual(model.call_count, 1)
            self.assertEqual(self.dialogs, [])

    def test_mobile_navigation_returns_with_unblocked_input(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(self.base + "/index.html")
        self.page.locator("#messageInput").fill("手机草稿")
        self.page.get_by_role("button", name="打开导航", exact=True).click()
        self.page.get_by_role("link", name="我的农药库", exact=True).click()
        self.view().get_by_role("button", name="打开导航", exact=True).click()
        self.view().get_by_role("navigation", name="主导航").get_by_role(
            "link", name="问智麦", exact=True
        ).click()
        expect(self.page.locator(".sidebar-backdrop")).to_be_hidden()
        self.page.locator("#messageInput").fill("手机回来后继续填写")
        expect(self.page.locator("#messageInput")).to_have_value("手机回来后继续填写")
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth > innerWidth")
        )
        self.assertEqual(self.dialogs, [])
