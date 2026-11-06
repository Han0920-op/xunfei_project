"""The screenshot's tagged control text must become a confirmed, scheduled reminder."""

import json, unittest
from datetime import timedelta
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import personal, memory, dialogue, config


class TaggedReminderBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def frame(self, target, closed=False):
        return (
            "<tool_call>"
            + json.dumps(
                {
                    "action": "tool",
                    "tool": "prepare_reminder",
                    "args": {
                        "name": "检查农作物",
                        "concern": "如有异常记录并补充相关图片",
                        "recurrence": "once",
                        "run_at": target.isoformat(),
                    },
                },
                ensure_ascii=False,
            )
            + ("</tool_call>" if closed else "")
        )

    def test_open_tag_becomes_confirmation_then_saved_plan_and_due_alert(self):
        target = personal.now() + timedelta(minutes=3)
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter(self.frame(target))
        ):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("帮我订一个检查农作物的闹钟")
            self.page.locator("#sendButton").click()
            expect(
                self.page.get_by_role("button", name="确认设置", exact=True)
            ).to_be_visible()
            expect(self.page.locator(".agent-answer")).not_to_contain_text(
                "<tool_call>"
            )
            expect(self.page.locator(".agent-answer")).not_to_contain_text("run_at")
            self.overflow()
        self.assertEqual(
            self.context.request.get(self.base + "/api/personal/tasks").json(), []
        )
        self.page.get_by_role("button", name="确认设置", exact=True).click()
        expect(self.page.locator(".reminder-draft")).to_contain_text("已设置，已保存")
        tasks = self.context.request.get(self.base + "/api/personal/tasks").json()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "检查农作物")
        self.page.get_by_role("link", name="去提醒页查看", exact=True).click()
        expect(self.page.frame_locator("iframe.app-navigation-view:not([hidden])").locator("article")).to_contain_text("检查农作物")
        with patch.object(personal, "now", return_value=target + timedelta(seconds=1)):
            personal.tick()
            personal.tick()
        self.page.goto(self.base + "/index.html")
        self.page.evaluate("ZhimaiReminders.refresh()")
        expect(self.page.locator("#reminderAlert")).to_contain_text("检查农作物")
        expect(self.page.locator("#reminderAlert")).to_contain_text("补充相关图片")
        self.assertEqual(
            len(
                self.context.request.get(
                    self.base + "/api/personal/notifications"
                ).json()
            ),
            1,
        )

    def test_old_raw_reply_is_not_executed_or_replayed_when_case_is_reopened(self):
        target = personal.now() + timedelta(minutes=4)
        raw = self.frame(target)
        memory.save_turn(
            self.who, "old-raw", "old-turn", "帮我订一个今晚的提醒", raw, [], [], False
        )
        self.page.goto(self.base + "/index.html?case=old-raw")
        expect(self.page.locator(".agent-answer")).to_contain_text("这条旧回复")
        expect(self.page.locator(".agent-answer")).not_to_contain_text("run_at")
        self.assertEqual(
            self.context.request.get(self.base + "/api/personal/tasks").json(), []
        )
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter(self.frame(target, True))

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            self.page.locator("#messageInput").fill("重新准备一次提醒")
            self.page.locator("#sendButton").click()
            expect(
                self.page.get_by_role("button", name="确认设置", exact=True)
            ).to_be_visible()
        self.assertNotIn(
            "<tool_call>{", json.dumps(captured[0][1:], ensure_ascii=False)
        )
        self.assertEqual(
            self.context.request.get(self.base + "/api/personal/tasks").json(), []
        )

    def test_broken_wrapper_keeps_input_without_exposing_or_saving_tool_payload(self):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm,
            "chat_stream",
            return_value=iter('<tool_call>{"action":"tool"'),
        ):
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill("帮我设置一个提醒")
            self.page.locator("#sendButton").click()
            expect(self.page.locator("#sendError")).to_contain_text("格式或证据自检")
            expect(self.page.locator("#messageInput")).to_have_value("帮我设置一个提醒")
            expect(self.page.locator(".reminder-draft")).to_have_count(0)
            expect(self.page.locator(".agent-answer")).to_have_count(0)
        self.assertEqual(
            self.context.request.get(self.base + "/api/personal/tasks").json(), []
        )


if __name__ == "__main__":
    unittest.main()
