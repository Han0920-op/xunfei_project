import base64, json, unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import config, llm, vision, web_search
from main import app


class DeepSeekTests(unittest.TestCase):
    def setUp(self):
        self.p = patch.multiple(
            config,
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="text-test-key",
            VISION_PROVIDER="deepseek",
            DEEPSEEK_VISION_BASE_URL="https://vision.example/v1",
            DEEPSEEK_VISION_API_KEY="vision-test-key",
        )
        self.p.start()
        self.addCleanup(self.p.stop)

    def response(self, data=None):
        r = MagicMock(status_code=200)
        r.__enter__.return_value = r
        r.iter_content.return_value = [json.dumps(data).encode()]
        return r

    def test_text_stream_uses_deepseek_key_model_and_drops_reasoning(self):
        r = self.response()
        r.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"reasoning_content":"private","content":"hello"}}]}',
            b"data: [DONE]",
        ]
        with patch.object(llm.requests, "post", return_value=r) as post:
            self.assertEqual(
                list(llm.chat_stream([{"role": "user", "content": "hi"}])), ["hello"]
            )
        self.assertEqual(
            post.call_args.args[0], "https://api.deepseek.com/chat/completions"
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer text-test-key"
        )
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-chat")
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        r.close.assert_called_once()

    def test_explicit_deepseek_missing_key_does_not_use_spark(self):
        with patch.object(config, "DEEPSEEK_API_KEY", ""), patch.object(
            config, "SPARK_API_PASSWORD", "old-key"
        ), patch.object(llm.requests, "post") as post:
            with self.assertRaises(llm.LLMError):
                list(llm.chat_stream([]))
            post.assert_not_called()

    def test_auto_migration_and_explicit_spark(self):
        with patch.object(config, "LLM_PROVIDER", "auto"):
            self.assertEqual(config.text_provider(), "deepseek")
            with patch.object(config, "DEEPSEEK_API_KEY", ""), patch.object(
                config, "SPARK_API_PASSWORD", "old-key"
            ):
                self.assertEqual(config.text_provider(), "spark")
        with patch.object(config, "LLM_PROVIDER", "spark"):
            self.assertEqual(config.text_provider(), "spark")

    def test_vision_sends_actual_image_with_separate_credentials(self):
        r = self.response(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "穗部局部发白，原因待核实"},
                    }
                ]
            }
        )
        data = b"\x89PNG\r\nimage-test"
        with patch.object(
            vision.requests, "post", return_value=r
        ) as post, patch.object(vision.websocket, "create_connection") as ws:
            self.assertIn("待核实", vision.understand_image(data, "观察可见症状"))
        ws.assert_not_called()
        self.assertEqual(
            post.call_args.args[0], "https://vision.example/v1/chat/completions"
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer vision-test-key"
        )
        content = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "观察可见症状")
        self.assertEqual(
            content[1]["image_url"]["url"],
            "data:image/png;base64," + base64.b64encode(data).decode(),
        )
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_official_text_endpoint_or_missing_vision_never_receives_photo(self):
        for url in ("", "https://api.deepseek.com/v1"):
            with self.subTest(url=url), patch.object(
                config, "DEEPSEEK_VISION_BASE_URL", url
            ), patch.object(vision.requests, "post") as post, patch.object(
                vision.websocket, "create_connection"
            ) as ws:
                with self.assertRaises(vision.VisionError):
                    vision.understand_image(b"jpeg", "photo")
                post.assert_not_called()
                ws.assert_not_called()

    def test_truncated_empty_and_failed_vision_are_not_observations(self):
        for d in (
            {
                "choices": [
                    {"finish_reason": "length", "message": {"content": "partial"}}
                ]
            },
            {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
            {"error": "private-token"},
        ):
            with patch.object(vision.requests, "post", return_value=self.response(d)):
                with self.assertRaises(vision.VisionError) as caught:
                    vision.understand_image(b"jpeg", "observe")
                self.assertNotIn("private-token", str(caught.exception))

    def test_capabilities_report_separate_providers_without_keys(self):
        data = TestClient(app).get("/api/agent/capabilities").json()
        self.assertEqual(data["chat_provider"], "deepseek")
        self.assertEqual(data["vision_provider"], "deepseek")
        self.assertNotIn("test-key", json.dumps(data))

    def test_search_keeps_query_and_wheat_context_without_inventing_diagnosis(self):
        with patch.object(
            web_search,
            "_search_web",
            return_value={"status": "unavailable", "results": []},
        ) as search:
            r = web_search.search_web("麦穗突然发白")
        search.assert_called_once_with("小麦 麦穗突然发白")
        self.assertEqual(r["query"], "小麦 麦穗突然发白")
        self.assertEqual(r["results"], [])
