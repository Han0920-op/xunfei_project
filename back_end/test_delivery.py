import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import requests
import config, dialogue, memory, personal, web_search, execution_plans, case_titles
from main import app
from runtime import STREAM_PROTOCOL
from response_stream import stream_response
from vision import gen_params


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(personal, "PATH", Path(self.tmp.name) / "db")
        self.patch.start()
        self.client = TestClient(app)
        self.client.get("/api/personal/session")
        self.who = self.client.cookies.get("zhimai_owner")

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def seed(self):
        memory.save_turn(
            self.who,
            "case",
            "first",
            "郑州的小麦穗部发白",
            "疑似问题待排查",
            [],
            [],
            False,
        )

    def chat(self, frames, message="联网查小麦症状", case="case", turn="turn"):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=[iter([x]) for x in frames]
        ):
            r = self.client.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"message": message, "case_id": case, "turn_id": turn},
            )
        return [
            json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")
        ]

    def test_title_with_checked_image_answer_and_safe_fallback(self):
        data = {
            "action": "answer",
            "title": "小麦赤霉病诊断",
            "verdict": "supported",
            "checks": dict(
                temporal_consistency=True,
                current_image_priority=True,
                health_claim_supported=True,
                action_supported=True,
            ),
            "issue_codes": [],
            "content": "穗部异常，需要排查。",
        }
        frame = list(
            stream_response(
                iter(json.dumps(data, ensure_ascii=False)), require_checks=True
            )
        )[-1]
        self.assertEqual(frame["title"], data["title"])
        self.assertEqual(case_titles.choose(frame["title"], "", []), "小麦疑似病害排查")
        self.assertEqual(case_titles.choose({"bad": 1}, "", []), "农事问题咨询记录")

    def test_title_persisted_only_once_and_history_kept(self):
        events = self.chat(
            [
                json.dumps(
                    {
                        "action": "answer",
                        "title": "小麦穗部异常排查",
                        "content": "请补拍穗轴。",
                    },
                    ensure_ascii=False,
                )
            ]
        )
        self.assertTrue(any(e["type"] == "case_title" for e in events))
        self.assertEqual(memory.get_case(self.who, "case")["title"], "小麦穗部异常排查")
        self.chat(["继续观察"], turn="second")
        case = memory.get_case(self.who, "case")
        self.assertEqual(len(case["turns"]), 2)
        self.assertEqual(case["title"], "小麦穗部异常排查")

    def test_title_storage_failure_does_not_fail_chat(self):
        with patch.object(case_titles, "save_once", side_effect=RuntimeError()):
            events = self.chat(["请补拍近照"])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(len(memory.get_case(self.who, "case")["turns"]), 1)

    def test_real_search_parser_filters_irrelevant_and_unsafe_links(self):
        body = b"<rss><channel><item><title>wheat symptoms</title><link>https://www.moa.gov.cn/example</link><description>wheat</description></item><item><title>wheat</title><link>javascript:alert(1)</link></item><item><title>NBA</title><link>https://espn.com/nba</link></item></channel></rss>"
        r = MagicMock()
        r.__enter__.return_value = r
        r.status_code = 200
        r.iter_content.return_value = [body]
        with patch.object(web_search.requests, "get", return_value=r):
            result = web_search.search_web("wheat")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["domain"], "www.moa.gov.cn")
        for url in [
            "javascript:alert(1)",
            "https://user:pass@example.com",
            "http://127.0.0.1",
            "https://example.com\n",
        ]:
            self.assertIsNone(web_search.safe_url(url))

    def test_official_fallback_fetches_actual_metadata_and_marks_historical(self):
        body = '<meta name="ArticleTitle" content="小麦赤霉病观察"><meta name="PubDate" content="2026-04-20"><div class="TRS_Editor">小麦赤霉病观察资料</div>'.encode()
        r = MagicMock()
        r.__enter__.return_value = r
        r.status_code = 200
        r.iter_content.return_value = [body]
        with patch.object(
            web_search, "_public_search", return_value={"status": "ok", "results": []}
        ), patch.object(
            web_search.requests, "get", side_effect=[r, requests.Timeout()]
        ):
            result = web_search.search_web("小麦赤霉病")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["published_on"], "2026-04-20")
        self.assertIn("历史", result["results"][0]["notice"])

    def test_search_timeout_events_correlate_and_chat_continues(self):
        call = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "小麦"}}
        )
        with patch.object(web_search.requests, "get", side_effect=requests.Timeout()):
            events = self.chat([call, "搜索失败，请补充资料。"])
        start = next(e for e in events if e["type"] == "tool_start")
        end = next(e for e in events if e["type"] == "tool_error")
        self.assertEqual(start["call_id"], end["call_id"])
        self.assertEqual(start["case_id"], "case")
        self.assertEqual(events[-1]["type"], "done")

    def test_plain_chat_has_no_search_event(self):
        events = self.chat(["你好"])
        self.assertFalse(any(e["type"] == "tool_start" for e in events))

    def test_plan_saved_via_agent_idempotent_owned_and_grounded(self):
        self.seed()
        payload = json.dumps(
            {
                "title": "小麦穗部异常排查",
                "crop": "小麦",
                "region": "郑州",
                "growth_stage": "开花期",
                "steps": ["photograph", "consult", "followup"],
            },
            ensure_ascii=False,
        )
        call = json.dumps(
            {
                "action": "tool",
                "tool": "save_execution_plan",
                "args": {"plan_json": payload},
            },
            ensure_ascii=False,
        )
        for _ in range(2):
            events = self.chat([call], message="为我生成一份执行方案")
        result = next(e["result"] for e in events if e["type"] == "tool_result")
        self.assertEqual(result["status"], "saved")
        rows = self.client.get("/api/plans").json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["region"], "郑州")
        self.assertEqual(rows[0]["growth_stage"], "待确认")
        other = TestClient(app)
        other.get("/api/personal/session")
        self.assertEqual(other.get("/api/plans").json(), [])
        self.assertEqual(other.get("/api/plans/" + result["plan_id"]).status_code, 404)
        self.client.delete("/api/memory/cases/case", headers={"X-Zhimai-Personal": "1"})
        self.assertEqual(self.client.get("/api/plans").json(), [])

    def test_plan_includes_current_turn_sources_and_explicit_user_context(self):
        self.seed()
        result = execution_plans.save(
            self.who,
            "case",
            "same-turn",
            json.dumps(
                {
                    "title": "小麦穗部异常排查",
                    "steps": ["observe"],
                    "growth_stage": "开花期",
                }
            ),
            [
                {
                    "tool": "search_web",
                    "result": {
                        "results": [
                            {
                                "title": "本轮资料",
                                "url": "https://www.moa.gov.cn/example",
                                "published_on": "2026-04-20",
                            }
                        ]
                    },
                }
            ],
            "现在是开花期",
        )
        plan = self.client.get("/api/plans/" + result["plan_id"]).json()
        self.assertEqual(plan["growth_stage"], "开花期")
        self.assertEqual(plan["references"][0]["title"], "本轮资料")

    def test_plan_arbitrary_drug_steps_rejected(self):
        self.seed()
        with self.assertRaises(ValueError):
            execution_plans.save(
                self.who,
                "case",
                "p",
                json.dumps({"title": "小麦药剂执行方案", "steps": ["喷药200克"]}),
            )
        self.assertEqual(self.client.get("/api/plans").json(), [])

    def test_model_image_payload_and_differential_prompt(self):
        data = gen_params("test", "观察症状", "BASE64")
        self.assertEqual(data["payload"]["message"]["text"][0]["content"], "BASE64")
        self.assertEqual(data["parameter"]["chat"]["domain"], "imagev3")
        self.assertIn("逐一比较", dialogue.VISION_QUESTION)
        self.assertIn("不能补造", dialogue.VISION_QUESTION)
