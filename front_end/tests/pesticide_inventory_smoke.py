"""Real owned inventory link and WP audit flow, with a fixed model only."""

import json, re, unittest
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import personal, dialogue, config


class InventoryNumberBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def save(self, id, name, number):
        r = self.context.request.put(
            self.base + "/api/personal/medicines/" + id,
            headers={"X-Zhimai-Personal": "1"},
            data={"name": name, "number": number},
        )
        self.assertEqual(r.status, 200)

    def test_selected_medicine_link_preserves_full_wp_number_without_selecting_other_stock(
        self,
    ):
        self.save("aerosol", "杀虫气雾剂", "WP20120033")
        self.save("other", "另一瓶药", "PD20250010")
        self.page.goto(self.base + "/personal.html?tab=medicines")
        self.page.locator(".personal-card").filter(
            has=self.page.get_by_role("heading", name="杀虫气雾剂", exact=True)
        ).get_by_role("link", name="带着这瓶药问智麦").click()
        expect(self.page.locator("#messageInput")).to_have_value(
            re.compile("WP20120033")
        )
        value = self.page.locator("#messageInput").input_value()
        self.assertNotIn("PD20250010", value)
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter(
                [
                    json.dumps(
                        {
                            "action": "tool",
                            "tool": "check_pesticide",
                            "args": {"registration_number": "WP20120033"},
                        }
                    )
                ]
            )

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer")).to_contain_text(
                "已识别完整登记号 WP20120033"
            )
            expect(self.page.locator(".agent-answer")).to_contain_text("卫生用")
            expect(self.page.locator(".agent-answer")).not_to_contain_text("号码不完整")
        self.assertIn("WP20120033", captured[0][-1]["content"])
        self.overflow()

    def test_generic_owned_single_wp_inventory_audit_does_not_repeat_number_question(
        self,
    ):
        self.save("aerosol", "杀虫气雾剂", "WP20120033")
        call = json.dumps({"action": "tool", "tool": "list_my_medicines", "args": {}})
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter([call])
        ) as model:
            self.page.goto(self.base + "/index.html")
            self.page.locator("#messageInput").fill(
                "请读取我的农药库，帮我核对手里的药。"
            )
            self.page.locator("#sendButton").click()
            expect(self.page.locator(".agent-answer")).to_contain_text(
                "本地资料尚未收录"
            )
            expect(self.page.locator(".agent-answer")).to_contain_text("无需重复")
            self.assertEqual(model.call_count, 1)
        self.overflow()


if __name__ == "__main__":
    unittest.main()
