"""A full WP code is user data, not an incomplete PD code or a wheat-use permit."""

import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from diagnostics import Trace
from runtime import STREAM_PROTOCOL
import personal, pesticides, dialogue, config
from main import app


class SanitaryRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(personal, "PATH", Path(self.tmp.name) / "db")
        self.p.start()
        self.a = TestClient(app)
        self.b = TestClient(app)
        self.h = {"X-Zhimai-Personal": "1"}
        for c in (self.a, self.b):
            c.get("/api/personal/session")

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def save(self):
        self.a.put(
            "/api/personal/medicines/aerosol",
            headers=self.h,
            json={"name": "杀虫气雾剂", "number": "wp20120033"},
        )

    def test_wp_normalizes_and_public_check_accepts_complete_number_without_target(
        self,
    ):
        self.assertEqual(pesticides.normalize_number(" wp20120033 "), "WP20120033")
        r = self.a.post(
            "/api/pesticides/check", json={"registration_number": "WP20120033"}
        )
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["number_status"], "recognized_format")
        self.assertEqual(d["status"], "not_in_local_catalog")
        self.assertFalse(d["recommendation_allowed"])
        self.assertIsNone(d["source"])
        self.assertIn("卫生用", d["summary"])
        self.assertIn("不代表官方没有登记", d["summary"])
        answer = pesticides.format_check_answer(r.text)
        self.assertNotIn("号码不完整", answer)
        self.assertIn("无需重复", answer)

    def test_bad_catalog_keeps_number_recognized_without_fabricating_registry_status(
        self,
    ):
        result = pesticides.check_registration(
            pesticides.CheckRequest(registration_number="WP20120033"),
            path="/missing-source",
        )
        self.assertEqual(result["status"], "source_unavailable")
        self.assertEqual(result["number_status"], "recognized_format")
        self.assertFalse(result["recommendation_allowed"])
        self.assertNotIn("2032", json.dumps(result))

    def test_inventory_mapping_is_owned_and_confirmed_format_is_explicit(self):
        self.save()
        trace = Trace()
        trace.owner = self.a.cookies.get("zhimai_owner")
        r = dialogue._tool_result("list_my_medicines", {}, set(), trace)
        self.assertEqual(r["medicines"][0]["registration_number"], "WP20120033")
        self.assertEqual(r["medicines"][0]["registration_kind"], "sanitary")
        self.assertIn("WP20120033", trace.inventory_registration_numbers)
        other = Trace()
        other.owner = self.b.cookies.get("zhimai_owner")
        self.assertEqual(
            dialogue._tool_result("list_my_medicines", {}, set(), other)["medicines"],
            [],
        )
        self.assertFalse(other.inventory_registration_numbers)

    def test_single_wp_inventory_audit_finishes_with_tool_result_not_bad_model_rephrasing(
        self,
    ):
        self.save()
        first = json.dumps({"action": "tool", "tool": "list_my_medicines", "args": {}})
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm,
            "chat_stream",
            side_effect=[iter([first]), iter(["号码不完整，请重新提供完整号码"])],
        ) as model:
            r = self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"message": "请读取我的农药库，帮我核对手里的药。"},
            )
        events = [
            json.loads(s[6:]) for s in r.text.splitlines() if s.startswith("data: ")
        ]
        self.assertEqual(model.call_count, 1)
        self.assertTrue(any(e.get("tool") == "check_pesticide" for e in events))
        answer = next(e["content"] for e in events if e["type"] == "answer")
        self.assertIn("WP20120033", answer)
        self.assertIn("卫生用", answer)
        self.assertNotIn("号码不完整", answer)
        self.assertIn("未实时连接", answer)

    def test_wp_photo_still_needs_user_confirmation(self):
        from test_dialogue import png

        call = json.dumps(
            {
                "action": "tool",
                "tool": "check_pesticide",
                "args": {"registration_number": "WP20120033"},
            }
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue, "understand_image", return_value="表格中可见登记号WP20120033"
        ), patch.object(dialogue.llm, "chat_stream", return_value=iter([call])):
            r = self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"message": "看看这张图片"},
                files={"image": ("x.png", png(), "image/png")},
            )
        self.assertIn("登记号尚未由用户确认", r.text)
        self.assertIn("WP20120033", r.text)
        self.assertTrue(
            dialogue.confirms_number(
                "确认",
                [
                    {
                        "role": "assistant",
                        "content": "请先对照包装确认：完整农药登记证号是 WP20120033 吗？",
                    }
                ],
                "WP20120033",
            )
        )

    def test_confirmed_inventory_number_does_not_trigger_photo_only_reconfirmation(
        self,
    ):
        self.save()
        calls = [
            iter(
                [
                    json.dumps(
                        {"action": "tool", "tool": "list_my_medicines", "args": {}}
                    )
                ]
            ),
            iter(
                [
                    json.dumps(
                        {
                            "action": "tool",
                            "tool": "check_pesticide",
                            "args": {
                                "registration_number": "WP20120033",
                                "target": "蚊",
                                "crop": "室内",
                            },
                        }
                    )
                ]
            ),
        ]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=calls
        ):
            r = self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"message": "读取农药库，看看家里这瓶药的信息"},
            )
        self.assertNotIn("登记号尚未由用户确认", r.text)
        self.assertIn("已识别完整登记号", r.text)

    def test_wp_is_not_made_valid_by_syntax_and_partial_or_script_codes_still_fail(
        self,
    ):
        for n in ("WP2012", "WP２０１２００３３", "WP20120033<script>", "INVALID"):
            with self.assertRaises(ValueError):
                pesticides.normalize_number(n)
        result = json.loads(pesticides.check_pesticide("WP20120033", target=""))
        self.assertEqual(result["number_status"], "recognized_format")
        self.assertFalse(result["recommendation_allowed"])


if __name__ == "__main__":
    unittest.main()
