"""Provider contract and bounded retry regression tests; no paid API calls."""

import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import config, llm, vision


class QwenRetryTests(unittest.TestCase):
    def setUp(self):
        p = patch.multiple(
            config,
            LLM_PROVIDER="qwen",
            VISION_PROVIDER="qwen",
            DASHSCOPE_API_KEY="bailian-test",
            QWEN_MODEL="qwen-plus",
            QWEN_VISION_MODEL="qwen-vl-plus",
            MODEL_CONNECT_RETRIES=1,
        )
        p.start()
        self.addCleanup(p.stop)

    def response(self, status=200, headers=None):
        r = MagicMock(status_code=status, headers=headers or {})
        r.__enter__.return_value = r
        r.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"answer"}}]}',
            b"data: [DONE]",
        ]
        r.iter_content.return_value = [
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "photo observation"},
                        }
                    ]
                }
            ).encode()
        ]
        return r

    def test_text_and_image_use_correct_models_and_same_bailian_key(self):
        with patch.object(
            llm.requests, "post", side_effect=[self.response(), self.response()]
        ) as post:
            self.assertEqual(list(llm.chat_stream([])), ["answer"])
            self.assertEqual(
                vision.understand_image(b"image", "observe"), "photo observation"
            )
        for call in post.call_args_list:
            self.assertEqual(call.args[0], config.QWEN_BASE_URL + "/chat/completions")
            self.assertEqual(
                call.kwargs["headers"]["Authorization"], "Bearer bailian-test"
            )
        self.assertEqual(
            [c.kwargs["json"]["model"] for c in post.call_args_list],
            ["qwen-plus", "qwen-vl-plus"],
        )
        self.assertIn(
            "base64,",
            post.call_args.kwargs["json"]["messages"][0]["content"][1]["image_url"][
                "url"
            ],
        )
        with patch.object(config, "VISION_PROVIDER", "auto"):
            self.assertEqual(config.vision_provider(), "qwen")

    def test_missing_key_never_falls_back_to_other_credentials(self):
        with patch.object(config, "DASHSCOPE_API_KEY", ""), patch.object(
            llm.requests, "post"
        ) as post:
            with self.assertRaises(llm.LLMError):
                list(llm.chat_stream([]))
            with self.assertRaises(vision.VisionError):
                vision.understand_image(b"photo", "observe")
            post.assert_not_called()

    def test_transient_failure_recovers_once_and_closes_responses(self):
        for failure in (
            llm.requests.ConnectionError(),
            self.response(503),
            self.response(429, {"Retry-After": "0"}),
        ):
            success = self.response()
            with patch.object(
                llm.requests, "post", side_effect=[failure, success]
            ) as post, patch.object(llm.time, "sleep"):
                self.assertEqual(list(llm.chat_stream([])), ["answer"])
                self.assertEqual(post.call_count, 2)
            success.close.assert_called_once()
            if not isinstance(failure, Exception):
                failure.close.assert_called_once()

    def test_retry_budget_and_unrecoverable_errors(self):
        for failure in (
            self.response(401),
            self.response(400),
            self.response(429, {"Retry-After": "20"}),
            self.response(503, {"Retry-After": "Wed, 01 Jan 2030 00:00:00 GMT"}),
            llm.requests.exceptions.ProxyError(),
            llm.requests.exceptions.SSLError(),
        ):
            with patch.object(
                llm.requests, "post", side_effect=[failure]
            ) as post, self.assertRaises(llm.LLMError):
                list(llm.chat_stream([]))
            self.assertEqual(post.call_count, 1)
        with patch.object(
            llm.requests, "post", side_effect=llm.requests.Timeout()
        ) as post, patch.object(llm.time, "sleep"), self.assertRaises(llm.LLMError):
            list(llm.chat_stream([]))
        self.assertEqual(post.call_count, 2)

    def test_partial_output_is_never_replayed(self):
        r = self.response()

        def lines(**kwargs):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}'
            raise llm.requests.Timeout()

        r.iter_lines.side_effect = lines
        with patch.object(llm.requests, "post", return_value=r) as post:
            stream = llm.chat_stream([])
            self.assertEqual(next(stream), "partial")
            with self.assertRaises(llm.LLMError):
                next(stream)
            self.assertEqual(post.call_count, 1)
        r.close.assert_called_once()

    def test_no_retry_when_turn_deadline_near(self):
        trace = SimpleNamespace(deadline=time.monotonic() + 2, log=MagicMock())
        with patch.object(
            llm.requests, "post", side_effect=llm.requests.Timeout()
        ) as post, self.assertRaises(llm.LLMError):
            list(llm.chat_stream([], trace=trace))
        self.assertEqual(post.call_count, 1)
