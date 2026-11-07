"""Chat probe verifies real transport and parser contracts without paid calls."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import config, llm
from urllib3.exceptions import ReadTimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_chat


class ChatProbeTests(unittest.TestCase):
    def setUp(self):
        p = patch.multiple(
            config,
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="private-key",
            DEEPSEEK_MODEL="deepseek-flash",
            DEEPSEEK_BASE_URL="https://api.deepseek.com",
        )
        p.start()
        self.addCleanup(p.stop)
        self.runtime_check = check_chat.runtime_check
        p = patch.object(
            check_chat, "runtime_check", return_value={"status": "matches"}
        )
        self.runtime = p.start()
        self.addCleanup(p.stop)

    def response(
        self, content='{"action":"answer","content":"private-answer"}', status=200
    ):
        r = MagicMock(status_code=status, headers={})
        r.iter_lines.return_value = [
            (
                "data: " + json.dumps({"choices": [{"delta": {"content": content}}]})
            ).encode(),
            b"data: [DONE]",
        ]
        r.json.return_value = {"choices": [{"message": {"content": "private-answer"}}]}
        return r

    def test_stream_success_uses_real_parser_and_never_prints_reply(self):
        r = self.response()
        with patch.object(llm.requests, "post", return_value=r) as post:
            result = check_chat.run()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer_format"], "ok")
        self.assertEqual(result["stream"]["http_status"], 200)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-flash")
        self.assertNotIn("private-", json.dumps(result))
        r.close.assert_called_once()

    def test_stream_fails_nonstream_succeeds_without_masking_failure(self):
        with patch.object(
            llm.requests,
            "post",
            side_effect=[llm.requests.ConnectionError("private-url"), self.response()],
        ) as post:
            result = check_chat.run()
        self.assertEqual(result["stream"]["status"], "model_connection_failed")
        self.assertEqual(result["nonstream"]["status"], "ok")
        self.assertNotEqual(result["status"], "ok")
        self.assertEqual(post.call_count, 2)
        self.assertTrue(post.call_args_list[0].kwargs["json"]["stream"])
        self.assertNotIn("stream", post.call_args_list[1].kwargs["json"])
        self.assertNotIn("private-", json.dumps(result))

    def test_bad_format_is_distinct_from_successful_transport(self):
        for content in (
            '{"action":"answer","content":',
            '{"action":"tool","tool":"prepare_reminder","args":{}}',
        ):
            with patch.object(
                llm.requests, "post", return_value=self.response(content)
            ) as post:
                result = check_chat.run()
            self.assertEqual(result["stream"]["status"], "ok")
            self.assertEqual(result["status"], "answer_format_invalid")
            self.assertEqual(post.call_count, 1)

    def test_billing_auth_and_config_errors_do_not_make_second_paid_call(self):
        for status, code in [
            (402, "model_payment_required"),
            (401, "model_auth_failed"),
            (400, "model_request_invalid"),
            (429, "model_rate_limited"),
        ]:
            r = self.response(status=status)
            with patch.object(llm.requests, "post", return_value=r) as post:
                result = check_chat.run()
            self.assertEqual(result["status"], code)
            self.assertEqual(result["stream"]["http_status"], status)
            self.assertEqual(post.call_count, 1)
            r.iter_lines.assert_not_called()
            r.json.assert_not_called()

    def test_wrapped_read_timeout_is_timeout_before_and_after_headers(self):
        def error():
            return llm.requests.ConnectionError(
                ReadTimeoutError(None, "/private-path", "private-error")
            )

        self.assertEqual(llm.connection_error(error()).code, "model_timeout")
        r = self.response()
        r.iter_lines.side_effect = error()
        for failure in (error(), r):
            with patch.object(
                llm.requests, "post", side_effect=[failure, self.response()]
            ) as post:
                result = check_chat.run()
            self.assertEqual(result["stream"]["status"], "model_timeout")
            self.assertEqual(post.call_count, 2)
            self.assertNotIn("private-", json.dumps(result))

    def test_runtime_comparison_only_returns_allowlisted_metadata(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "server_version": "old",
                "chat_provider": "spark",
                "chat_model": "old-model",
                "unexpected": "private-key",
            }
        ).encode()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(check_chat, "build_opener", return_value=opener):
            result = self.runtime_check(config.text_settings())
        self.assertEqual(result["status"], "model_config_differs")
        self.assertFalse(result["version_matches"])
        self.assertNotIn("private-", json.dumps(result))

    def test_invalid_endpoint_never_sends_key(self):
        with patch.object(
            config, "DEEPSEEK_BASE_URL", "https://user:private@example.com"
        ), patch.object(llm.requests, "post") as post:
            self.assertEqual(check_chat.run()["status"], "model_endpoint_invalid")
            post.assert_not_called()

    def test_wrapped_timeout_after_partial_text_is_not_retried(self):
        r = self.response()

        def lines(**kwargs):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}'
            raise llm.requests.ConnectionError(
                ReadTimeoutError(None, "/private", "private-error")
            )

        r.iter_lines.side_effect = lines
        with patch.object(llm.requests, "post", return_value=r) as post:
            stream = llm.chat_stream([])
            self.assertEqual(next(stream), "partial")
            with self.assertRaises(llm.LLMError) as caught:
                next(stream)
            self.assertEqual(caught.exception.code, "model_timeout")
            self.assertEqual(post.call_count, 1)
