"""Real browser chat → automatic stock save → inventory; models are test doubles."""

import json
import unittest
from unittest.mock import patch

from playwright.sync_api import expect

import casework_smoke as helper
import config
import dialogue
import personal


class ChatInventoryBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def call(self, text, names):
        return json.dumps(
            {
                "action": "tool",
                "tool": "save_my_medicines",
                "args": {
                    "medicines_json": json.dumps(
                        [{"name": n, "source_quote": text} for n in names],
                        ensure_ascii=False,
                    )
                },
            },
            ensure_ascii=False,
        )

    def send(self, text):
        self.page.locator("#messageInput").fill(text)
        self.page.locator("#sendButton").click()

    def test_batch_save_receipt_repeat_dedup_and_delete_in_inventory(self):
        text = "我手里有多菌灵、吡虫啉"
        call = self.call(text, ["多菌灵", "吡虫啉"])
        script = [
            iter([call]),
            iter(["已记录手里的两种药，使用前仍需核对。"]),
            iter([call]),
            iter(["这两种药已经记录，没有重复添加。"]),
        ]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=script
        ):
            self.page.goto(self.base + "/index.html")
            self.send(text)
            receipt = self.page.get_by_role("region", name="农药入库结果")
            expect(receipt).to_contain_text("多菌灵")
            expect(receipt).to_contain_text("吡虫啉")
            expect(receipt).to_contain_text("登记证号待补充")
            self.overflow()
            self.send(text)
            expect(receipt.last).to_contain_text("已有记录，未重复添加")
            self.assertEqual(len(personal.listing(self.who, "medicines")), 2)
            receipt.last.get_by_role("link", name="查看、编辑我的农药库").click()
            expect(self.page.locator(".personal-card")).to_have_count(2)
            self.page.locator(".personal-card").filter(
                has=self.page.get_by_role("heading", name="多菌灵", exact=True)
            ).get_by_role("button", name="删除", exact=True).click()
            self.page.get_by_role("button", name="确认删除", exact=True).click()
            expect(self.page.locator(".personal-card")).to_have_count(1)
            self.assertEqual(
                personal.listing(self.who, "medicines")[0]["name"], "吡虫啉"
            )
            self.overflow()

    def test_question_does_not_write_even_if_model_requests_save(self):
        text = "我手里有多菌灵吗？"
        script = [
            iter([self.call(text, ["多菌灵"])]),
            iter(["请先说明你实际持有的药，尚未添加。"]),
        ]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=script
        ):
            self.page.goto(self.base + "/index.html")
            self.send(text)
            expect(self.page.locator(".agent-answer")).to_contain_text("尚未添加")
            expect(self.page.locator(".inventory-receipt")).to_have_count(0)
            self.assertEqual(personal.listing(self.who, "medicines"), [])

    def test_saved_inventory_remains_visible_as_error_notice_after_answer_failure(self):
        text = "我手里有多菌灵"
        script = [iter([self.call(text, ["多菌灵"])]), ValueError("model interrupted")]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=script
        ):
            self.page.goto(self.base + "/index.html")
            self.send(text)
            expect(self.page.locator("#sendError")).to_contain_text(
                "药品资料已保存到“我的农药库”"
            )
            expect(self.page.locator("#messageInput")).to_have_value(text)
            self.assertEqual(len(personal.listing(self.who, "medicines")), 1)
            self.page.goto(self.base + "/personal.html?tab=medicines")
            expect(
                self.page.get_by_role("heading", name="多菌灵", exact=True)
            ).to_be_visible()


if __name__ == "__main__":
    unittest.main()
