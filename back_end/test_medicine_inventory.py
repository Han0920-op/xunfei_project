"""Owned chat writes, source boundaries, idempotency and failure behavior."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import config
import dialogue
import medicine_inventory as inventory
import personal
from diagnostics import Trace
from main import app
from runtime import STREAM_PROTOCOL


class ChatInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = patch.object(personal, "PATH", Path(self.tmp.name) / "db")
        self.path.start()
        self.client = TestClient(app)
        self.client.get("/api/personal/session")
        self.who = self.client.cookies.get("zhimai_owner")

    def tearDown(self):
        self.path.stop()
        self.tmp.cleanup()

    def payload(self, name="多菌灵", quote="我手里有多菌灵", number=""):
        return json.dumps(
            [{"name": name, "number": number, "source_quote": quote}],
            ensure_ascii=False,
        )

    def save(self, text="我手里有多菌灵", payload=None, who=None):
        return inventory.save_reported(who or self.who, text, payload or self.payload())

    def events(
        self,
        text,
        payload,
        *,
        reply="已记录。登记号未知，可到我的农药库补充。",
        history=None,
        **form
    ):
        call = json.dumps(
            {
                "action": "tool",
                "tool": "save_my_medicines",
                "args": {"medicines_json": payload},
            }
        )
        script = (
            [iter([call]), iter([reply])]
            if isinstance(reply, str)
            else [iter([call]), reply]
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=script
        ):
            response = self.client.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"message": text, "history": json.dumps(history or []), **form},
            )
        self.assertEqual(response.status_code, 200)
        return [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]

    def test_batch_saved_through_chat_readable_on_inventory_and_isolated(self):
        text = "我手里有多菌灵、吡虫啉"
        payload = json.dumps(
            [{"name": n, "source_quote": text} for n in ("多菌灵", "吡虫啉")],
            ensure_ascii=False,
        )
        events = self.events(text, payload, case_id="owned-case", turn_id="owned-turn")
        result = next(e["result"] for e in events if e["type"] == "tool_result")
        self.assertEqual(result["status"], "saved")
        self.assertEqual(events[-1]["type"], "done")
        rows = self.client.get("/api/personal/medicines").json()
        self.assertEqual({r["name"] for r in rows}, {"多菌灵", "吡虫啉"})
        self.assertTrue(
            all(r["number"] == "" and "用户自述" in r["notes"] for r in rows)
        )
        other = TestClient(app)
        other.get("/api/personal/session")
        self.assertEqual(other.get("/api/personal/medicines").json(), [])

    def test_questions_negation_plans_third_party_quotes_and_opt_out_cannot_write(self):
        for text in [
            "我手里有什么药？",
            "我手里有多菌灵吗？",
            "我手里有多菌灵？",
            "我没有多菌灵",
            "我想买多菌灵",
            "邻居手里有多菌灵",
            "如果我手里有多菌灵",
            "他说：我手里有多菌灵",
            "示例：我手里有多菌灵",
            "我手里有多菌灵，不要保存",
            "我手里有多菌灵，不用记录",
            "我手里有用完的多菌灵",
        ]:
            with self.subTest(text=text):
                result = self.save(text, self.payload(quote=text))
                self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(personal.listing(self.who, "medicines"), [])

    def test_only_current_user_text_not_history_or_image_can_supply_medicine(self):
        history = [{"role": "user", "content": "我手里有多菌灵"}]
        events = self.events("帮我看看照片", self.payload(), history=history)
        self.assertEqual(
            next(e["result"]["status"] for e in events if e["type"] == "tool_result"),
            "needs_clarification",
        )
        self.assertEqual(personal.listing(self.who, "medicines"), [])
        self.assertEqual(
            self.save("我手里有多菌灵", self.payload("吡虫啉", "图片里写着吡虫啉"))[
                "status"
            ],
            "needs_clarification",
        )

    def test_question_after_positive_clause_and_other_negative_clause(self):
        for text in [
            "我手里有多菌灵，能用吗？",
            "我手里有多菌灵，但没有吡虫啉",
            "家里有多菌灵",
            "刚买了多菌灵",
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    self.save(text, self.payload(quote=text.split("，")[0]))["status"],
                    "saved",
                )
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)
        result = self.save(
            "我手里有多菌灵，但没有吡虫啉", self.payload("吡虫啉", "吡虫啉")
        )
        self.assertEqual(result["status"], "needs_clarification")

    def test_repeat_and_concurrent_requests_do_not_duplicate(self):
        self.save()
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(lambda _: self.save(), range(8)))
        self.assertTrue(all(r["medicines"][0]["action"] == "existing" for r in results))
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)

    def test_natural_possession_after_symptoms_or_label_confirmation(self):
        for text, quote in [
            ("小麦叶子发黄了。我手里有多菌灵", "我手里有多菌灵"),
            ("我手里的药是多菌灵", "我手里的药是多菌灵"),
            ("我这有多菌灵", "我这有多菌灵"),
            ("我手上还有多菌灵", "我手上还有多菌灵"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    self.save(text, self.payload(quote=quote))["status"], "saved"
                )
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)

    def test_explicit_number_enriches_name_only_and_keeps_different_labels(self):
        self.save()
        text = "我手里有多菌灵 pd20250010"
        result = self.save(text, self.payload(quote=text, number="pd20250010"))
        self.assertEqual(result["medicines"][0]["action"], "updated")
        self.assertEqual(
            personal.listing(self.who, "medicines")[0]["number"], "PD20250010"
        )
        self.save(text, self.payload(quote=text, number="PD20250010"))
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)
        other = "我手里有多菌灵 PD20250011"
        self.save(other, self.payload(quote=other, number="PD20250011"))
        self.assertEqual(len(personal.listing(self.who, "medicines")), 2)

    def test_number_alias_dedup_preserves_manual_notes_and_number(self):
        self.client.put(
            "/api/personal/medicines/manual",
            headers={"X-Zhimai-Personal": "1"},
            json={
                "name": "我的气雾剂",
                "number": "WP20120033",
                "notes": "保留这条备注",
            },
        )
        text = "我手里有杀虫气雾剂 WP20120033"
        result = self.save(text, self.payload("杀虫气雾剂", text, "WP20120033"))
        self.assertEqual(result["medicines"][0]["action"], "existing")
        rows = personal.listing(self.who, "medicines")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["notes"], "保留这条备注")

    def test_unknown_fabricated_number_generic_name_or_injected_owner_rejects_batch(
        self,
    ):
        for payload in [
            self.payload(number="PD20250010"),
            self.payload(number="not-a-number"),
            self.payload("农药", "我手里有农药"),
            '[{"name":"多菌灵","source_quote":"我手里有多菌灵","owner":"another"}]',
            "[]",
            '{"name":"多菌灵"}',
        ]:
            self.assertEqual(
                self.save(payload=payload)["status"], "needs_clarification"
            )
        self.assertEqual(personal.listing(self.who, "medicines"), [])
        self.assertEqual(
            inventory.save_reported(None, "我手里有多菌灵", self.payload())["status"],
            "unavailable",
        )

    def test_capacity_failure_rolls_back_entire_batch(self):
        with personal.db() as c:
            for i in range(99):
                c.execute(
                    "INSERT INTO entries VALUES(?,?,?,?,?)",
                    (
                        self.who,
                        str(i),
                        "medicines",
                        json.dumps({"name": "原有药" + str(i)}),
                        "",
                    ),
                )
        text = "我手里有多菌灵、吡虫啉"
        trace = Trace()
        trace.owner, trace.current_user_message = self.who, text
        payload = json.dumps(
            [{"name": n, "source_quote": text} for n in ("多菌灵", "吡虫啉")],
            ensure_ascii=False,
        )
        result = dialogue._tool_result(
            "save_my_medicines", {"medicines_json": payload}, set(), trace
        )
        self.assertEqual(result["status"], "full")
        self.assertEqual(len(personal.listing(self.who, "medicines")), 99)

    def test_failed_later_answer_does_not_undo_saved_inventory_and_retry_dedups(self):
        events = self.events(
            "我手里有多菌灵", self.payload(), reply=ValueError("model failed")
        )
        self.assertEqual(
            next(e["result"]["status"] for e in events if e["type"] == "tool_result"),
            "saved",
        )
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)
        self.events("我手里有多菌灵", self.payload())
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)

    def direct_chat(self, text, model_script=(), **form):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model_script
        ) as model:
            response = self.client.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"message": text, **form},
            )
        self.assertEqual(response.status_code, 200)
        return [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ], model.call_count

    def test_explicit_save_with_number_does_not_need_model_or_registration_check(self):
        text = "我手里有贝莱斯芽孢杆菌C17271，包装登记证号是PD20250010。请把它记到我的农药库里"
        events, count = self.direct_chat(text)
        self.assertEqual(count, 0)
        rows = personal.listing(self.who, "medicines")
        self.assertEqual(
            [(r["name"], r["number"]) for r in rows],
            [("贝莱斯芽孢杆菌C17271", "PD20250010")],
        )
        self.assertEqual(
            [e["tool"] for e in events if e["type"] == "tool_result"],
            ["save_my_medicines"],
        )
        self.assertIn(
            "已保存", next(e["content"] for e in events if e["type"] == "answer")
        )
        self.assertEqual(events[-1]["type"], "done")
        repeated, _ = self.direct_chat(text)
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)
        self.assertIn(
            "未重复添加", next(e["content"] for e in repeated if e["type"] == "answer")
        )

    def test_combined_request_saves_before_models_registration_check_ends_turn(self):
        text = "我手里有贝莱斯芽孢杆菌C17271，包装登记证号是PD20250010。请把它记到我的农药库里，再按小麦赤霉病核对能不能用。"
        call = json.dumps(
            {
                "action": "tool",
                "tool": "check_pesticide",
                "args": {
                    "registration_number": "PD20250010",
                    "crop": "小麦",
                    "target": "赤霉病",
                },
            }
        )
        events, count = self.direct_chat(text, [iter([call])])
        self.assertEqual(count, 1)
        self.assertEqual(
            [e["tool"] for e in events if e["type"] == "tool_result"],
            ["save_my_medicines", "check_pesticide"],
        )
        answer = next(e["content"] for e in events if e["type"] == "answer")
        self.assertIn("已保存", answer)
        self.assertIn("未核实", answer)
        self.assertEqual(len(personal.listing(self.who, "medicines")), 1)

    def test_explicit_save_failure_never_claims_success(self):
        with patch.object(
            inventory, "save_reported", side_effect=RuntimeError("private-db-path")
        ):
            events, count = self.direct_chat("我手里有多菌灵，请把它记到我的农药库里")
        self.assertEqual(count, 0)
        answer = next(e["content"] for e in events if e["type"] == "answer")
        self.assertIn("保存失败", answer)
        self.assertNotIn("已保存", answer)
        self.assertNotIn("private-db-path", json.dumps(events))
        self.assertEqual(personal.listing(self.who, "medicines"), [])

    def test_explicit_route_rejects_uncertain_negated_quoted_and_ambiguous_items(self):
        for text in [
            "如果我手里有多菌灵，请记到我的农药库里",
            "邻居说我手里有多菌灵，请记到我的农药库里",
            "我手里有多菌灵吗？请记到我的农药库里",
            "我手里有多菌灵，请不要记到我的农药库里",
            "我手里有多菌灵，请别存入我的农药库里",
            "我手里有多菌灵和吡虫啉，请记到我的农药库里",
            "我手里有多菌灵、吡虫啉，请记到我的农药库里",
            "我手里有多菌灵，邻居有吡虫啉PD20250010。请记到我的农药库里",
            "请把图片里的药记到我的农药库里",
            "请把上次说的药记到我的农药库里",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(inventory.explicit_save_request(text))


if __name__ == "__main__":
    unittest.main()
