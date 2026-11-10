"""Owned, persisted plan progress; completion never changes diagnosis or reminders."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import execution_plans, memory, personal
from main import app

HEADERS = {"X-Zhimai-Personal": "1"}


class PlanProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = patch.object(personal, "PATH", Path(self.tmp.name) / "data.db")
        self.path.start()
        self.client = TestClient(app)
        self.client.get("/api/personal/session")
        self.who = self.client.cookies.get("zhimai_owner")
        memory.save_turn(
            self.who, "case", "turn", "郑州的小麦穗部异常", "需要排查", [], [], False
        )
        result = execution_plans.save(
            self.who,
            "case",
            "plan",
            json.dumps(
                {"title": "穗部排查", "steps": ["photograph", "observe", "followup"]}
            ),
        )
        self.url = "/api/plans/" + result["plan_id"]

    def tearDown(self):
        self.client.close()
        self.path.stop()
        self.tmp.cleanup()

    def update(self, number, completed, revision, client=None):
        return (client or self.client).patch(
            f"{self.url}/steps/{number}",
            headers=HEADERS,
            json={"completed": completed, "revision": revision},
        )

    def test_legacy_plan_progress_completion_and_undo_are_persisted(self):
        initial = self.client.get(self.url).json()
        self.assertEqual(initial["revision"], 0)
        self.assertEqual(initial["progress"], {"completed": 0, "total": 3})
        first = self.update(1, True, 0).json()
        self.assertEqual(first["status"], "in_progress")
        self.assertTrue(first["steps"][0]["completed_at"])
        self.assertEqual(self.client.get(self.url).json()["progress"]["completed"], 1)
        second = self.update(2, True, 1).json()
        third = self.update(3, True, second["revision"]).json()
        self.assertEqual(third["status"], "completed")
        self.assertEqual(
            self.client.get("/api/plans").json()[0]["progress"]["completed"], 3
        )
        self.assertFalse(memory.get_case(self.who, "case")["archived"])
        self.assertEqual(memory.facts(self.who, "case"), [])
        self.assertEqual(personal.listing(self.who, "tasks"), [])
        undone = self.update(2, False, third["revision"]).json()
        self.assertEqual(undone["status"], "in_progress")
        self.assertIsNone(undone["steps"][1]["completed_at"])
        self.assertEqual(undone["diagnosis_summary"], initial["diagnosis_summary"])

    def test_noop_does_not_increment_revision(self):
        result = self.update(1, False, 0).json()
        self.assertEqual(result["revision"], 0)
        updated = self.update(1, True, 0).json()
        again = self.update(1, True, updated["revision"]).json()
        self.assertEqual(again["revision"], updated["revision"])
        self.assertEqual(
            again["steps"][0]["completed_at"], updated["steps"][0]["completed_at"]
        )

    def test_stale_and_concurrent_updates_do_not_overwrite_other_steps(self):
        other = TestClient(app)
        other.cookies.set("zhimai_owner", self.who)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.update, 1, True, 0),
                pool.submit(self.update, 2, True, 0, other),
            ]
            results = [f.result() for f in futures]
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        current = self.client.get(self.url).json()
        self.assertEqual(current["progress"]["completed"], 1)
        self.assertEqual(current["revision"], 1)
        remaining = next(
            s["number"] for s in current["steps"][:2] if not s["completed"]
        )
        self.assertEqual(self.update(remaining, True, 0).status_code, 409)
        self.assertEqual(
            self.update(remaining, True, 1).json()["progress"]["completed"], 2
        )
        other.close()

    def test_ownership_header_and_strict_fields(self):
        other = TestClient(app)
        other.get("/api/personal/session")
        self.assertEqual(self.update(1, True, 0, other).status_code, 404)
        self.assertEqual(
            self.client.patch(
                self.url + "/steps/1", json={"completed": True, "revision": 0}
            ).status_code,
            403,
        )
        for payload in (
            {"completed": "true", "revision": 0},
            {"completed": True, "revision": False},
            {"completed": True, "revision": 0, "title": "overwrite"},
        ):
            self.assertEqual(
                self.client.patch(
                    self.url + "/steps/1", headers=HEADERS, json=payload
                ).status_code,
                422,
            )
        self.assertEqual(self.update(99, True, 0).status_code, 404)
        self.assertEqual(self.client.get(self.url).json()["revision"], 0)
        other.close()

    def test_archived_and_deleted_cases_cannot_update(self):
        r = self.client.patch(
            "/api/memory/cases/case",
            headers=HEADERS,
            json={"title": "穗部排查", "archived": True},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.client.get(self.url).json()["case_archived"])
        self.assertEqual(self.update(1, True, 0).status_code, 409)
        self.client.delete("/api/memory/cases/case", headers=HEADERS)
        self.assertEqual(self.update(1, True, 0).status_code, 404)
        self.assertEqual(self.client.get("/api/plans").json(), [])
