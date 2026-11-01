"""Case state provenance, deletion, private photos and scheduler closure races."""

import io, json, tempfile, unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
import casework, personal, memory, dialogue, config
from diagnostics import Trace
from runtime import STREAM_PROTOCOL
from main import app


class CaseworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(personal, "PATH", Path(self.tmp.name) / "test.db")
        self.p.start()
        self.a = TestClient(app)
        self.b = TestClient(app)
        self.h = {"X-Zhimai-Personal": "1"}
        for client in (self.a, self.b):
            client.get("/api/personal/session")
        self.who = self.a.cookies.get("zhimai_owner")

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def save(self, case="case", turn="t1", assessment=None, photo=None, tools=None):
        memory.save_turn(
            self.who,
            case,
            turn,
            "叶片黄化",
            "暂不能确诊",
            [{"status": "ok", "content": "可见黄叶，不能确诊"}] if photo else [],
            tools or [],
            bool(photo),
            "p-" + turn,
            photo,
            assessment,
        )

    def assessment(self):
        return {
            "symptoms": "叶片黄化",
            "growth_stage": "用户未确认",
            "candidate_causes": ["病害或非生物因素，尚不能区分"],
            "missing_information": ["新叶是否也变黄？"],
            "review_required": False,
        }

    def test_thirty_incomplete_scenarios_stop_after_three_effective_rounds(self):
        # Workflow acceptance, not a model accuracy or agronomic evaluation.
        symptoms = [
            "幼苗黄叶",
            "老叶发黄",
            "叶尖焦枯",
            "白色粉状物",
            "条状黄斑",
            "叶鞘褐斑",
            "疑似虫体",
            "根部发黑",
            "全株萎蔫",
            "零散缺苗",
        ]
        for i in range(30):
            with self.subTest(
                symptom=symptoms[i % 10], clarity=["模糊", "远景", "清晰局部"][i // 10]
            ):
                case = "fixture-" + str(i)
                for n in range(3):
                    a = self.assessment()
                    a["symptoms"] = symptoms[i % 10]
                    a = casework.prepare_assessment(self.who, case, a)
                    self.save(case, str(i) + "-" + str(n), a)
                state = casework.snapshot(self.who, case)["state"]
                self.assertEqual(state["clarification_rounds"], 3)
                self.assertEqual(state["status"], "escalated")
                self.assertTrue(state["review_required"])
                self.assertEqual(memory.facts(self.who, case), [])
                trace = Trace()
                trace.owner = self.who
                trace.case_id = case
                result = dialogue._tool_result(
                    "record_case_assessment",
                    {"assessment_json": json.dumps(self.assessment())},
                    set(),
                    trace,
                )
                self.assertTrue(result["assessment"]["review_required"])

    def test_structured_model_tool_is_saved_only_when_answer_completes(self):
        draft = json.dumps(
            {
                "action": "tool",
                "tool": "record_case_assessment",
                "args": {
                    "assessment_json": json.dumps(self.assessment(), ensure_ascii=False)
                },
            },
            ensure_ascii=False,
        )
        responses = [iter([draft]), iter(["请补充新叶情况，目前不能确诊。"])]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=responses
        ):
            r = self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"case_id": "chat", "turn_id": "turn", "message": "黄叶了"},
            )
        self.assertIn("memory_saved", r.text)
        state = casework.snapshot(self.who, "chat")["state"]
        self.assertEqual(state["status"], "needs_information")
        self.assertFalse(state["assessment"]["confirmed"])
        responses = [iter([draft]), RuntimeError("private model error")]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=responses
        ):
            r = self.a.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={"case_id": "failed", "turn_id": "turn2", "message": "黄叶了"},
            )
        self.assertEqual(self.a.get("/api/memory/cases/failed").status_code, 404)

    def test_duplicate_turn_is_idempotent_for_events_rounds_and_photos(self):
        for _ in range(2):
            self.save(assessment=self.assessment(), photo=b"compressed-jpeg")
        data = casework.snapshot(self.who, "case")
        self.assertEqual(len(data["photos"]), 1)
        self.assertEqual(len(data["events"]), 2)
        self.assertEqual(data["state"]["clarification_rounds"], 1)

    def test_photo_upload_compresses_strips_exif_and_checks_ownership(self):
        self.save()
        im = Image.new("RGB", (20, 20), "green")
        out = io.BytesIO()
        exif = Image.Exif()
        exif[270] = "private GPS-like metadata"
        im.save(out, format="JPEG", exif=exif)
        r = self.a.post(
            "/api/casework/cases/case/photos",
            files={"image": ("x.jpg", out.getvalue(), "image/jpeg")},
            headers=self.h,
        )
        self.assertEqual(r.status_code, 200)
        path = casework.snapshot(self.who, "case")["photos"][0]["serverUrl"]
        photo = self.a.get(path)
        self.assertEqual(photo.headers["cache-control"], "private, no-store")
        self.assertNotIn(b"private GPS", photo.content)
        self.assertEqual(self.b.get(path).status_code, 404)
        self.assertEqual(
            self.b.post(
                "/api/casework/cases/case/photos",
                files={"image": ("x.jpg", out.getvalue(), "image/jpeg")},
                headers=self.h,
            ).status_code,
            404,
        )

    def task(self):
        return {
            "name": "补图复查",
            "task_type": "followup",
            "case_id": "case",
            "recurrence": "once",
            "run_at": (personal.now() + timedelta(minutes=10)).isoformat(),
            "notes": "观察新叶并补图",
        }

    def test_followup_bound_case_edit_due_dedup_and_close_cancellation(self):
        self.save()
        task = self.task()
        self.assertEqual(
            self.b.put(
                "/api/personal/tasks/foreign", headers=self.h, json=task
            ).status_code,
            409,
        )
        self.assertEqual(
            self.a.put(
                "/api/personal/tasks/follow", headers=self.h, json=task
            ).status_code,
            200,
        )
        task["run_at"] = (personal.now() + timedelta(hours=2)).isoformat()
        self.a.put("/api/personal/tasks/follow", headers=self.h, json=task)
        with patch.object(
            personal, "now", return_value=personal.now() + timedelta(hours=1)
        ):
            personal.tick()
        self.assertEqual(personal.listing(self.who, "notifications"), [])
        with patch.object(
            personal, "now", return_value=personal.now() + timedelta(hours=3)
        ):
            personal.tick()
            personal.tick()
        notes = personal.listing(self.who, "notifications")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["case_id"], "case")
        task["run_at"] = (personal.now() + timedelta(hours=4)).isoformat()
        self.a.put("/api/personal/tasks/follow", headers=self.h, json=task)
        self.a.put(
            "/api/casework/cases/case/state", json={"status": "closed"}, headers=self.h
        )
        with patch.object(
            personal, "now", return_value=personal.now() + timedelta(hours=5)
        ):
            personal.tick()
        self.assertEqual(len(personal.listing(self.who, "notifications")), 1)
        self.assertFalse(personal.listing(self.who, "tasks")[0]["enabled"])

    def test_closed_case_cannot_be_reopened_by_late_chat_and_delete_cascades(self):
        self.save(photo=b"compressed")
        self.a.put("/api/personal/tasks/f", headers=self.h, json=self.task())
        self.a.put(
            "/api/casework/cases/case/state", json={"status": "closed"}, headers=self.h
        )
        with self.assertRaises(personal.HTTPException):
            self.save(turn="late")
        casework.build_report(self.who, "case")
        self.a.delete("/api/memory/cases/case", headers=self.h)
        with memory.db() as c:
            for t in ("case_events", "case_states", "case_photos", "case_reports"):
                self.assertEqual(
                    c.execute(f"SELECT count(*) FROM {t}").fetchone()[0], 0
                )
        self.assertEqual(personal.listing(self.who, "tasks"), [])

    def test_worse_feedback_escalates_does_not_claim_drug_effect_or_auto_schedule(self):
        self.save()
        r = self.a.post(
            "/api/casework/cases/case/feedback",
            json={"change": "worse", "notes": "黄化扩大", "measures": "实际只补拍照片"},
            headers=self.h,
        )
        self.assertEqual(r.json()["state"]["status"], "escalated")
        self.assertTrue(r.json()["state"]["review_required"])
        self.assertEqual(
            memory.facts(self.who, "case")[0]["source_type"], "user_confirmed"
        )
        self.assertEqual(personal.listing(self.who, "tasks"), [])

    def test_comparison_requires_two_successful_observations_and_current_photo_is_included(
        self,
    ):
        self.save(photo=b"clean1")
        self.assertEqual(
            casework.compare(self.who, "case")["status"], "insufficient_evidence"
        )
        result = casework.compare(self.who, "case", "当前黄叶更明显，角度不同")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["after"]["pending_save"])
        self.save(turn="t2", photo=b"clean2")
        self.assertEqual(casework.compare(self.who, "case")["status"], "ok")

    def test_report_keeps_source_snapshots_blocks_unverified_medication_and_escapes_html(
        self,
    ):
        self.save(
            assessment=self.assessment(),
            tools=[
                {
                    "tool": "check_pesticide",
                    "result": {
                        "use_decision": "hold_for_verification",
                        "reason_codes": ["status_unverified"],
                        "source": {"title": "<script>private</script>"},
                    },
                }
            ],
        )
        r = self.a.post("/api/casework/cases/case/reports", headers=self.h)
        report = r.json()
        self.assertFalse(report["medication_decision"]["allowed"])
        self.assertTrue(report["references"])
        self.assertTrue(report["rule_checks"])
        self.assertIn("模型", report["cause_source"])
        url = "/api/casework/cases/case/reports/" + report["id"]
        self.assertEqual(self.b.get(url).status_code, 404)
        self.assertEqual(self.b.get(url + "/print").status_code, 404)
        printed = self.a.get(url + "/print")
        self.assertIn("&lt;script&gt;", printed.text)
        self.assertNotIn("<script>", printed.text)
        self.assertEqual(self.a.get(url).json(), report)

    def test_reusing_photo_identifier_cannot_attach_different_pixels_to_old_observation(
        self,
    ):
        self.save(photo=b"clean-first")
        with self.assertRaises(personal.HTTPException):
            memory.save_turn(
                self.who,
                "case",
                "t2",
                "new",
                "answer",
                [],
                [],
                True,
                "p-t1",
                b"different-image",
            )
        self.assertEqual(len(memory.get_case(self.who, "case")["turns"]), 1)

    def test_followup_draft_needs_confirmation_and_never_guesses_interval(self):
        self.save()
        trace = Trace()
        trace.owner = self.who
        trace.case_id = "case"
        r = dialogue._tool_result(
            "prepare_followup",
            {"run_at": self.task()["run_at"], "concern": "补拍叶背"},
            set(),
            trace,
        )
        self.assertEqual(r["status"], "draft")
        self.assertEqual(r["case_id"], "case")
        self.assertEqual(personal.listing(self.who, "tasks"), [])
        self.assertEqual(
            dialogue._tool_result(
                "prepare_followup", {"concern": "复查"}, set(), trace
            )["error"],
            "invalid_arguments",
        )


if __name__ == "__main__":
    unittest.main()
