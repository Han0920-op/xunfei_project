import json, unittest
from unittest.mock import patch
import dialogue, config, llm
from response_stream import stream_response, ResponseFormatError
from test_answer_review import checked


class StabilityTests(unittest.TestCase):
    def run_frames(self, frames, history=None):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=[iter([f]) for f in frames]
        ) as model:
            events = list(dialogue.run_turn("帮我联网搜索一下", history or []))
        return events, model.call_count

    def test_content_first_checked_object_and_omitted_default(self):
        d = json.loads(checked("请补拍穗轴。"))
        d.pop("issue_codes")
        d = {"content": d.pop("content"), **d}
        events = list(
            stream_response(
                iter(json.dumps(d, ensure_ascii=False)), require_checks=True
            )
        )
        self.assertEqual(events[-1]["content"], "请补拍穗轴。")
        d = json.loads(checked("正常输出"))
        d.pop("issue_codes")
        self.assertEqual(
            list(stream_response(iter(json.dumps(d)), require_checks=True))[-1][
                "content"
            ],
            "正常输出",
        )

    def test_fenced_single_json_tools_only_after_full_completion(self):
        f = (
            "```json\n"
            + json.dumps(
                {"action": "tool", "tool": "search_web", "args": {"query": "小麦"}}
            )
            + "\n```"
        )
        events = list(stream_response(iter(f), require_checks=True))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"]["tool"], "search_web")
        for extra in ["解释", "\n" + f]:
            with self.assertRaises(ResponseFormatError):
                list(stream_response(iter(f + extra)))

    def test_content_first_false_checks_never_leak(self):
        d = json.loads(checked("危险建议"))
        d["checks"]["action_supported"] = False
        d = {"content": d.pop("content"), **d}
        events = []
        with self.assertRaises(ResponseFormatError):
            for e in stream_response(iter(json.dumps(d)), require_checks=True):
                events.append(e)
        self.assertEqual(events, [])

    def test_missing_checks_repaired_once_with_no_rejected_answer_leak(self):
        events, count = self.run_frames(
            ["普通未核对回答", checked("未取得足够依据，请说明要查什么。")],
            [{"role": "assistant", "content": "此前该轮图片的初步观察"}],
        )
        self.assertEqual(count, 2)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(any(e["type"] == "answer_reset" for e in events))
        self.assertFalse(any("普通未核对" in e.get("content", "") for e in events))

    def test_search_failure_finishes_without_second_model_call(self):
        f = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "赤霉病"}}
        )
        with patch.object(
            dialogue.tools.TOOLS["search_web"],
            "func",
            return_value='{"status":"unavailable","results":[]}',
        ):
            events, count = self.run_frames([f])
        self.assertEqual(count, 1)
        self.assertEqual(events[-1]["type"], "done")
        self.assertIn(
            "未能取得", next(e["content"] for e in events if e["type"] == "answer")
        )

    def test_completed_search_not_repeated_when_final_format_fails(self):
        f = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "赤霉病"}}
        )
        with patch.object(
            dialogue.tools.TOOLS["search_web"],
            "func",
            return_value=json.dumps(
                {
                    "status": "ok",
                    "results": [{"title": "资料", "url": "https://www.moa.gov.cn/x"}],
                }
            ),
        ) as search:
            events, count = self.run_frames([f, '{"action":', '{"action":'])
        self.assertEqual(search.call_count, 1)
        self.assertEqual(count, 3)
        self.assertEqual(events[-1]["type"], "done")
        self.assertIn(
            "仅说明实际执行状态",
            next(e["content"] for e in events if e["type"] == "answer"),
        )

    def test_invalid_registration_argument_is_recoverable_not_internal_error(self):
        f = json.dumps(
            {
                "action": "tool",
                "tool": "check_pesticide",
                "args": {"registration_number": {"bad": 1}},
            }
        )
        events, count = self.run_frames([f, "请提供完整登记号。"])
        self.assertEqual(events[-1]["type"], "done")
        self.assertFalse(any(e["type"] == "error" for e in events))
        self.assertFalse(any(e["type"] == "tool_start" for e in events))

    def test_auth_errors_are_not_retried(self):
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm,
            "chat_stream",
            side_effect=llm.LLMError("auth", "model_auth_failed"),
        ) as m:
            events = list(dialogue.run_turn("你好", []))
        self.assertEqual(m.call_count, 1)
        self.assertEqual(events[-1]["code"], "model_auth_failed")


class CompletedRetryTests(unittest.TestCase):
    def test_committed_request_replays_without_model_and_rejects_changed_input(self):
        import tempfile
        from pathlib import Path
        from fastapi.testclient import TestClient
        import personal, memory
        from main import app
        from runtime import STREAM_PROTOCOL

        with tempfile.TemporaryDirectory() as folder, patch.object(
            personal, "PATH", Path(folder) / "db"
        ):
            client = TestClient(app)
            client.get("/api/personal/session")
            who = client.cookies.get("zhimai_owner")
            memory.save_turn(
                who, "case", "turn", "查询天气", "已完成查询", [], [], False
            )
            with patch.object(dialogue.llm, "chat_stream") as model:
                response = client.post(
                    "/api/agent/chat",
                    headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                    data={"message": "查询天气", "case_id": "case", "turn_id": "turn"},
                )
                self.assertIn("已完成查询", response.text)
                model.assert_not_called()
                changed = client.post(
                    "/api/agent/chat",
                    headers={"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                    data={
                        "message": "改成别的内容",
                        "case_id": "case",
                        "turn_id": "turn",
                    },
                )
                self.assertEqual(changed.status_code, 409)

    def test_photo_replay_checks_image_and_owner(self):
        import io, tempfile
        from pathlib import Path
        from PIL import Image
        from fastapi.testclient import TestClient
        import personal, memory
        from main import app
        from chat_api import prepare_image
        from runtime import STREAM_PROTOCOL

        def photo(color):
            out = io.BytesIO()
            Image.new("RGB", (24, 24), color).save(out, format="PNG")
            return out.getvalue()

        original = photo("green")
        with tempfile.TemporaryDirectory() as folder, patch.object(
            personal, "PATH", Path(folder) / "db"
        ):
            client = TestClient(app)
            client.get("/api/personal/session")
            who = client.cookies.get("zhimai_owner")
            memory.save_turn(
                who,
                "photo-case",
                "photo-turn",
                "看看照片",
                "需要补拍",
                [{"type": "vision_result", "status": "ok", "content": "观察"}],
                [],
                True,
                "photo-id",
                prepare_image(original, "image/png"),
            )
            args = {
                "headers": {"X-Zhimai-Stream-Protocol": STREAM_PROTOCOL},
                "data": {
                    "message": "看看照片",
                    "case_id": "photo-case",
                    "turn_id": "photo-turn",
                    "photo_id": "photo-id",
                },
            }
            with patch.object(dialogue.llm, "chat_stream") as model:
                response = client.post(
                    "/api/agent/chat",
                    **args,
                    files={"image": ("x.png", original, "image/png")}
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("需要补拍", response.text)
                changed = client.post(
                    "/api/agent/chat",
                    **args,
                    files={"image": ("x.png", photo("red"), "image/png")}
                )
                self.assertEqual(changed.status_code, 409)
                stranger = TestClient(app)
                stranger.get("/api/personal/session")
                response = stranger.post(
                    "/api/agent/chat",
                    **args,
                    files={"image": ("x.png", original, "image/png")}
                )
                self.assertNotEqual(response.status_code, 200)
                model.assert_not_called()
