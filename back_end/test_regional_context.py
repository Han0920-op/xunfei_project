"""Owned region references, ambiguity and grounded chat context; no live models."""

import json, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import personal, agri_sources, regional_context, memory, dialogue, config
from main import app
from runtime import STREAM_PROTOCOL


class RegionalContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = patch.object(personal, "PATH", Path(self.tmp.name) / "regional.db")
        self.path.start()
        self.now = datetime(2026, 11, 1, 12, tzinfo=personal.TZ)
        self.clock = patch.object(personal, "now", return_value=self.now)
        self.clock.start()
        self.a = TestClient(app)
        self.b = TestClient(app)
        self.h = {"X-Zhimai-Personal": "1"}
        for client in (self.a, self.b):
            client.get("/api/personal/session")
        self.who = self.a.cookies.get("zhimai_owner")

    def tearDown(self):
        self.clock.stop()
        self.path.stop()
        self.tmp.cleanup()

    def subscribe(self, id="zz", province="河南", city="郑州", enabled=True):
        r = self.a.put(
            "/api/intelligence/subscriptions/" + id,
            headers=self.h,
            json={
                "province": province,
                "city": city,
                "pests": ["条锈病"],
                "enabled": enabled,
            },
        )
        self.assertEqual(r.status_code, 200)

    def doc(self, id="valid", **kw):
        d = {
            "id": id,
            "url": "https://www.moa.gov.cn/xw/zwdt/202611/" + id + ".htm",
            "title": "测试情报：河南条锈病",
            "kind": "bulletin",
            "published_on": "2026-11-01",
            "valid_until": "2026-11-08",
            "retrieved_at": self.now.isoformat(),
            "regions": ["河南"],
            "pests": ["条锈病"],
            "review_status": "metadata_reviewed",
            "agronomic_review": "pending_review",
            "text": "private raw text",
            "review_note": "private operator note",
            "sha256": "test",
        } | kw
        with agri_sources.db() as c:
            agri_sources.ensure(c)
            c.execute(
                "INSERT INTO official_documents VALUES(?,?,?)",
                (id, d["url"], json.dumps(d)),
            )

    def chat(self, selected="", message="今天有什么需要留意？", case="case"):
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter(["请结合本次实际情况观察，地区背景只作参考。"])

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            r = self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={
                    "message": message,
                    "case_id": case,
                    "turn_id": case + "-t",
                    "region_subscription_id": selected,
                },
            )
        events = [
            json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")
        ]
        return r, events, captured

    def test_no_subscription_then_single_active_reference_and_explicit_disable(self):
        self.assertEqual(
            regional_context.context(self.who)["status"], "no_subscription"
        )
        self.subscribe()
        c = regional_context.context(self.who)
        self.assertEqual(c["selected"]["city"], "郑州")
        self.assertIn("不证明照片拍摄地", c["notice"])
        self.assertIsNone(regional_context.context(self.who, "none")["selected"])
        disabled = regional_context.prompt_context(
            regional_context.context(self.who, "none")
        )
        self.assertEqual(disabled["candidate_regions"], [])
        self.assertNotIn("郑州", json.dumps(disabled, ensure_ascii=False))
        self.subscribe(enabled=False)
        self.assertEqual(
            regional_context.context(self.who)["status"], "no_subscription"
        )

    def test_multiple_subscriptions_never_choose_first_and_are_isolated(self):
        self.subscribe()
        self.subscribe("jn", "山东", "济南")
        c = regional_context.context(self.who)
        self.assertEqual(c["status"], "needs_selection")
        self.assertIsNone(c["selected"])
        self.assertEqual(c["bulletins"], [])
        self.assertEqual(
            regional_context.context(self.who, "jn")["selected"]["city"], "济南"
        )
        self.assertEqual(
            self.b.get("/api/intelligence/chat-context").json()["options"], []
        )
        with self.assertRaises(personal.HTTPException):
            regional_context.context(self.b.cookies.get("zhimai_owner"), "zz")

    def test_expired_stale_other_region_and_city_signals_do_not_enter_prompt(self):
        self.subscribe()
        self.doc()
        self.doc("expired", valid_until="2026-10-31")
        self.doc("future", published_on="2026-11-02")
        self.doc("other", regions=["山东"])
        self.doc("city", cities=["濮阳"])
        self.doc("pest", pests=["蚜虫"])
        self.doc("stale", retrieved_at=(self.now - timedelta(days=2)).isoformat())
        self.doc("pending", review_status="pending_metadata_review")
        self.doc("guide", kind="guideline")
        c = regional_context.context(self.who)
        self.assertEqual([d["id"] for d in c["bulletins"]], ["valid"])
        text = json.dumps(regional_context.prompt_context(c))
        self.assertNotIn("private raw text", text)
        self.assertNotIn("private operator note", text)

    def test_sse_context_saved_separately_from_facts_and_survives_case_reload(self):
        self.subscribe()
        r, events, captured = self.chat()
        self.assertEqual(r.status_code, 200)
        context = next(e for e in events if e["type"] == "regional_context")
        self.assertEqual(context["selected"]["id"], "zz")
        text = json.dumps(captured[0], ensure_ascii=False)
        self.assertIn("郑州", text)
        self.assertIn("照片拍摄地", text)
        case = memory.get_case(self.who, "case")
        self.assertEqual(case["facts"], [])
        self.assertEqual(case["state"]["reference_region"]["selected"]["id"], "zz")
        self.assertEqual(
            case["turns"][0]["assistant"]["regionalContext"]["selected"]["city"], "郑州"
        )

    def test_current_explicit_location_remains_last_question_and_can_override_reference(
        self,
    ):
        self.subscribe()
        message = "我这次问山东济南的天气，照片也在济南拍的。"
        r, events, captured = self.chat(message=message)
        self.assertIn(message, captured[0][-1]["content"])
        self.assertIn("当前用户文字明确其他地点时优先该地点", captured[0][0]["content"])
        self.assertEqual(memory.facts(self.who, "case"), [])

    def test_multiple_choice_none_and_paused_or_foreign_id_fail_before_model(self):
        self.subscribe()
        self.subscribe("jn", "山东", "济南")
        _, events, _ = self.chat(selected="jn")
        self.assertEqual(
            next(e for e in events if e["type"] == "regional_context")["selected"][
                "city"
            ],
            "济南",
        )
        _, events, _ = self.chat(selected="none", case="none")
        self.assertEqual(
            next(e for e in events if e["type"] == "regional_context")["status"],
            "disabled",
        )
        self.subscribe("jn", "山东", "济南", enabled=False)
        r, _, captured = self.chat(selected="jn", case="paused")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(captured, [])
        r, _, captured = self.chat(selected="foreign", case="foreign")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(captured, [])

    def test_previous_region_snapshot_is_not_reinjected_as_current_context(self):
        self.subscribe()
        self.chat()
        self.subscribe("jn", "山东", "济南")
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter(["按本次所选济南作为参考。"])

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={
                    "message": "本次参考济南",
                    "case_id": "case",
                    "turn_id": "second",
                    "region_subscription_id": "jn",
                },
            )
        state = next(
            m["content"]
            for m in captured[0]
            if m["content"].startswith("【当前案例进度")
        )
        self.assertNotIn("reference_region", state)
        self.assertEqual(
            memory.get_case(self.who, "case")["state"]["reference_region"]["selected"][
                "city"
            ],
            "济南",
        )

    def test_context_lookup_has_no_weather_side_effect_or_notification(self):
        self.subscribe()
        with patch.object(
            personal.weather,
            "get_weather",
            side_effect=AssertionError("no automatic weather call"),
        ):
            r = self.a.get("/api/intelligence/chat-context")
            self.assertEqual(r.status_code, 200)
        self.assertEqual(personal.listing(self.who, "notifications"), [])


if __name__ == "__main__":
    unittest.main()
