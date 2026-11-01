"""Region selection travels through real HTTP and survives owned case recovery."""

from unittest.mock import patch
import json, unittest
from playwright.sync_api import expect
import casework_smoke as helper
import config, dialogue, memory, personal


# Reuse server lifecycle without inheriting unrelated case tests into discovery.
class RegionalBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def sub(self, id="zz", province="河南", city="郑州"):
        r = self.context.request.put(
            self.base + "/api/intelligence/subscriptions/" + id,
            headers={"X-Zhimai-Personal": "1"},
            data={"province": province, "city": city, "pests": ["条锈病"]},
        )
        self.assertEqual(r.status, 200)

    def send(self, text):
        self.page.locator("#messageInput").fill(text)
        self.page.locator("#sendButton").click()

    def test_single_reference_saved_then_multiple_choices_and_none(self):
        self.sub()
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter(["根据本次明确的地点核对天气和资料，订阅只作参考。"])

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            self.page.goto(self.base + "/index.html")
            expect(self.page.get_by_label("本次参考地区", exact=True)).to_be_visible()
            self.overflow()
            self.assertIn(
                "郑州", self.page.get_by_label("本次参考地区", exact=True).inner_text()
            )
            self.send("帮我参考订阅地区，看看有什么需要留意")
            expect(self.page.locator(".agent-answer")).to_contain_text("订阅只作参考")
            self.assertIn("郑州", json.dumps(captured[-1], ensure_ascii=False))
            case_id = self.page.evaluate("FarmerStore.records()[0].id")
            self.assertEqual(
                memory.get_case(self.who, case_id)["state"]["reference_region"][
                    "selected"
                ]["id"],
                "zz",
            )
            self.sub("jn", "山东", "济南")
            self.page.goto(self.base + "/index.html")
            expect(self.page.get_by_label("本次参考地区", exact=True)).to_be_visible()
            self.page.get_by_label("本次参考地区", exact=True).select_option("jn")
            self.send("本次参考济南")
            expect(self.page.locator(".agent-answer")).to_be_visible()
            c = self.page.evaluate("FarmerStore.records()[0].id")
            self.assertEqual(
                memory.get_case(self.who, c)["state"]["reference_region"]["selected"][
                    "id"
                ],
                "jn",
            )
            self.page.goto(self.base + "/index.html?case=" + c)
            expect(self.page.get_by_label("本次参考地区", exact=True)).to_have_value(
                "jn"
            )
            self.page.get_by_label("本次参考地区", exact=True).select_option("none")
            self.send("这次不参考订阅地区")
            expect(self.page.locator("#sendButton")).to_be_enabled()
            expect(self.page.get_by_label("本次参考地区", exact=True)).to_have_value(
                "none"
            )
            self.assertEqual(
                memory.get_case(self.who, c)["state"]["reference_region"]["status"],
                "disabled",
            )
            self.overflow()

    def test_multiple_regions_no_selection_keeps_ambiguity_and_reference_is_not_fact(
        self,
    ):
        self.sub()
        self.sub("jn", "山东", "济南")
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter(["你想参考郑州还是济南？"])

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            self.page.goto(self.base + "/index.html")
            expect(self.page.get_by_label("本次参考地区", exact=True)).to_be_visible()
            expect(self.page.get_by_label("本次参考地区", exact=True)).to_have_value("")
            self.send("帮我查天气")
            expect(self.page.locator(".agent-answer")).to_have_text(
                "你想参考郑州还是济南？"
            )
            case_id = self.page.evaluate("FarmerStore.records()[0].id")
            c = memory.get_case(self.who, case_id)
            self.assertEqual(
                c["state"]["reference_region"]["status"], "needs_selection"
            )
            self.assertEqual(c["facts"], [])
            expect(self.page.locator(".agent-evidence")).to_have_count(0)
            self.overflow()


if __name__ == "__main__":
    unittest.main()
