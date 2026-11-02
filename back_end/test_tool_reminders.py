"""Regression for the photographed <tool_call> output: card, save, due delivery."""

import json, tempfile, unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import config, dialogue, personal, memory
from runtime import STREAM_PROTOCOL
from main import app


class TaggedReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = patch.object(personal, "PATH", Path(self.tmp.name) / "db")
        self.path.start()
        self.client = TestClient(app)
        self.client.get("/api/personal/session")
        self.who = self.client.cookies.get("zhimai_owner")
        self.target = personal.now() + timedelta(minutes=5)

    def tearDown(self):
        self.path.stop()
        self.tmp.cleanup()

    def frame(self, closing=True):
        return (
            "<tool_call>"
            + json.dumps(
                {
                    "action": "tool",
                    "tool": "prepare_reminder",
                    "args": {
                        "name": "检查农作物",
                        "concern": "检查农作物情况，如有异常记录并补充相关图片",
                        "recurrence": "once",
                        "run_at": self.target.isoformat(),
                        "time": "20:00",
                    },
                },
                ensure_ascii=False,
            )
            + ("</tool_call>" if closing else "")
        )

    def request(self, raw, history=None, case_id=""):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter(raw)
        ):
            return self.client.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={
                    "message": "帮我订一个检查农作物的提醒",
                    "history": json.dumps(history or []),
                    "case_id": case_id,
                    "turn_id": "tagged-turn" if case_id else "",
                },
            )

    def test_open_only_and_closed_frames_produce_draft_without_saving_until_confirmed(
        self,
    ):
        for closing in (False, True):
            with self.subTest(closing=closing):
                r = self.request(self.frame(closing))
                events = [
                    json.loads(l[6:])
                    for l in r.text.splitlines()
                    if l.startswith("data: ")
                ]
                draft = next(
                    e["result"]
                    for e in events
                    if e["type"] == "tool_result" and e["tool"] == "prepare_reminder"
                )
                self.assertEqual(draft["status"], "draft")
                self.assertEqual(personal.listing(self.who, "tasks"), [])
                self.assertFalse(
                    any(
                        "<tool_call>" in e.get("content", "")
                        or "run_at" in e.get("content", "")
                        for e in events
                        if e["type"] in ("answer", "answer_delta")
                    )
                )
        body = {k: v for k, v in draft.items() if k in personal.Entry.model_fields}
        response = self.client.put(
            "/api/personal/tasks/confirmed",
            headers={"X-Zhimai-Personal": "1"},
            json=body,
        )
        self.assertEqual(response.status_code, 200)
        with patch.object(
            personal, "now", return_value=self.target + timedelta(seconds=1)
        ):
            personal.tick()
            personal.tick()
        self.assertEqual(len(personal.listing(self.who, "notifications")), 1)

    def test_image_history_does_not_prevent_private_wrapped_tool_from_being_dispatched(
        self,
    ):
        history = [
            {
                "role": "assistant",
                "content": "【此前该轮图片的初步观察，非本轮新识别】叶尖黄化【此前回答】未确诊",
            }
        ]
        self.assertIn('"status": "draft"', self.request(self.frame(), history).text)

    def test_malformed_wrapper_never_yields_answer_or_creates_task(self):
        r = self.request(self.frame() + "额外文字")
        events = [
            json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")
        ]
        self.assertEqual(events[-1]["type"], "error")
        self.assertFalse(
            any(e["type"] in ("answer", "answer_delta", "tool_call") for e in events)
        )
        self.assertEqual(personal.listing(self.who, "tasks"), [])

    def test_server_history_never_replays_old_unexecuted_tool_text_as_created_task(
        self,
    ):
        memory.save_turn(
            self.who,
            "old-case",
            "old-turn",
            "设置今晚提醒",
            self.frame(False),
            [],
            [],
            False,
        )
        captured = []

        def model(messages, **kwargs):
            captured.append(messages)
            return iter([self.frame()])

        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=model
        ):
            r = self.client.post(
                "/api/agent/chat",
                headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                data={
                    "message": "重新设置提醒",
                    "case_id": "old-case",
                    "turn_id": "new-turn",
                },
            )
        self.assertIn('"status": "draft"', r.text)
        self.assertNotIn(
            "<tool_call>{", json.dumps(captured[0][1:], ensure_ascii=False)
        )
        self.assertEqual(personal.listing(self.who, "tasks"), [])


if __name__ == "__main__":
    unittest.main()
