"""Model IDs here are fixtures, not a claim about the current official catalog."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import config, llm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_model


class ModelProbeTests(unittest.TestCase):
    def setUp(self):
        self.p = patch.multiple(
            config,
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="secret-test-value",
            DEEPSEEK_MODEL="deepseek-flash",
            DEEPSEEK_BASE_URL="https://api.deepseek.com",
        )
        self.p.start()
        self.addCleanup(self.p.stop)

    def response(self, data, status=200):
        r = MagicMock(status_code=status)
        r.__enter__.return_value = r
        r.iter_content.return_value = [json.dumps(data).encode()]
        return r

    def test_model_id_is_verified_against_live_response_not_hardcoded(self):
        r = self.response({"data": [{"id": "deepseek-flash"}]})
        with patch.object(check_model.requests, "get", return_value=r) as get:
            result = check_model.probe()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["selected_model_available"])
        self.assertEqual(get.call_args.args[0], "https://api.deepseek.com/models")
        self.assertNotIn("secret-test-value", json.dumps(result))
        self.assertEqual(llm._payload([])["model"], "deepseek-flash")

    def test_absent_model_reports_actual_ids_without_guessing(self):
        with patch.object(
            check_model.requests,
            "get",
            return_value=self.response({"data": [{"id": "fixture-other-model"}]}),
        ):
            result = check_model.probe()
        self.assertEqual(result["status"], "model_not_listed")
        self.assertEqual(result["available_models"], ["fixture-other-model"])

    def test_network_failures_distinguished_in_probe_and_chat(self):
        cases = [
            (
                llm.requests.exceptions.ProxyError("secret-proxy-url"),
                "model_proxy_failed",
            ),
            (llm.requests.exceptions.SSLError("secret-cert-path"), "model_tls_failed"),
            (
                llm.requests.exceptions.ConnectionError("secret-destination"),
                "model_connection_failed",
            ),
        ]
        for exc, code in cases:
            with self.subTest(code=code), patch.object(
                llm.requests, "post", side_effect=exc
            ), patch.object(check_model.requests, "get", side_effect=exc):
                with self.assertRaises(llm.LLMError) as caught:
                    list(llm.chat_stream([]))
                self.assertEqual(caught.exception.code, code)
                result = check_model.probe()
                self.assertEqual(result["status"], code)
                self.assertNotIn("secret-", json.dumps(result))

    def test_bad_endpoint_does_not_send_key(self):
        for base in (
            "api.deepseek.com",
            "https://api.deepseek.com/chat/completions",
            "https://user:secret@example.com",
        ):
            with patch.object(config, "DEEPSEEK_BASE_URL", base), patch.object(
                check_model.requests, "get"
            ) as get:
                self.assertEqual(
                    check_model.probe()["status"], "model_endpoint_invalid"
                )
                get.assert_not_called()

    def test_http_error_does_not_expose_body(self):
        r = self.response({"message": "secret-service-body"}, 401)
        with patch.object(check_model.requests, "get", return_value=r):
            result = check_model.probe()
        self.assertEqual(result["status"], "model_auth_failed")
        self.assertEqual(result["http_status"], 401)
        self.assertNotIn("secret-", json.dumps(result))
        r.iter_content.assert_not_called()

    def test_invalid_model_response_safe(self):
        with patch.object(
            check_model.requests,
            "get",
            return_value=self.response({"other": "secret-body"}),
        ):
            result = check_model.probe()
        self.assertEqual(result["status"], "model_list_invalid")
        self.assertNotIn("secret-", json.dumps(result))

    def test_qwen_probe_uses_bailian_endpoint_and_key(self):
        with patch.multiple(
            config,
            LLM_PROVIDER="qwen",
            DASHSCOPE_API_KEY="bailian-test",
            QWEN_MODEL="qwen-plus",
        ), patch.object(
            check_model.requests,
            "get",
            return_value=self.response({"data": [{"id": "qwen-plus"}]}),
        ) as get:
            result = check_model.probe()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(get.call_args.args[0], config.QWEN_BASE_URL + "/models")
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], "Bearer bailian-test"
        )
        self.assertNotIn("bailian-test", json.dumps(result))

    def test_large_catalog_checks_all_ids_before_display_limit(self):
        rows = [{"id": "a-model-" + str(i)} for i in range(110)] + [
            {"id": "deepseek-flash"}
        ]
        with patch.object(
            check_model.requests, "get", return_value=self.response({"data": rows})
        ):
            result = check_model.probe()
        self.assertEqual(result["status"], "ok")
        self.assertIn("deepseek-flash", result["available_models"])
