"""Synchronous image transport lifecycle tests; no real sockets or credentials."""
import base64
import json
import ssl
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import websocket

import config
import vision


def packet(content="", status=2, code=0):
    return json.dumps({
        "header": {"code": code},
        "payload": {"choices": {"status": status, "text": [{"content": content}]}},
    }, ensure_ascii=False)


class VisionTransportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(config, "XFYUN_APP_ID", "test-app"))
        self.stack.enter_context(patch.object(config, "XFYUN_API_KEY", "test-api-key"))
        self.stack.enter_context(patch.object(config, "XFYUN_API_SECRET", "test-api-secret"))
        self.connection = Mock()
        self.connect = self.stack.enter_context(patch.object(vision.websocket, "create_connection", return_value=self.connection))

    def test_partial_chunks_and_final_are_merged_with_verified_tls(self):
        self.connection.recv.side_effect = [packet("叶片有", 0), packet("白色粉层", 1), packet("，近景不清。", 2)]
        answer = vision.understand_image(b"image bytes", "观察小麦")
        self.assertEqual(answer, "叶片有白色粉层，近景不清。")
        self.connect.assert_called_once()
        kwargs = self.connect.call_args.kwargs
        self.assertEqual(kwargs["sslopt"]["cert_reqs"], ssl.CERT_REQUIRED)
        self.assertGreater(kwargs["timeout"], 0)
        self.assertLessEqual(kwargs["timeout"], 15)
        timeouts = [args.args[0] for args in self.connection.settimeout.call_args_list]
        self.assertEqual(len(timeouts), 3)
        self.assertTrue(all(0 < t <= 15 for t in timeouts))
        self.connection.close.assert_called_once()

    def test_sent_payload_contains_current_photo_and_requested_question(self):
        self.connection.recv.return_value = packet("观察结果")
        vision.understand_image(b"current image", "只观察可见部位")
        payload = json.loads(self.connection.send.call_args.args[0])
        messages = payload["payload"]["message"]["text"]
        self.assertEqual(base64.b64decode(messages[0]["content"]), b"current image")
        self.assertEqual(messages[0]["content_type"], "image")
        self.assertEqual(messages[1]["content"], "只观察可见部位")

    def test_provider_error_does_not_leak_response_or_signed_url(self):
        self.connection.recv.return_value = json.dumps({"header": {"code": 10001, "message": "secret-provider-body authorization=test-api-secret"}})
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertNotIn("secret-provider-body", str(caught.exception))
        self.assertNotIn("test-api-secret", str(caught.exception))
        self.connection.close.assert_called_once()

    def test_empty_eof_does_not_become_successful_empty_observation(self):
        self.connection.recv.return_value = ""
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertIn("完整", str(caught.exception))
        self.connection.close.assert_called_once()

    def test_partial_result_followed_by_eof_is_not_returned_as_complete(self):
        self.connection.recv.side_effect = [packet("只有半句", 1), ""]
        with self.assertRaises(vision.VisionError):
            vision.understand_image(b"image", "看看")
        self.assertEqual(self.connection.recv.call_count, 2)
        self.connection.close.assert_called_once()

    def test_final_whitespace_is_not_an_observation(self):
        self.connection.recv.return_value = packet("  \n ", 2)
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertIn("可用观察", str(caught.exception))
        self.connection.close.assert_called_once()

    def test_socket_timeout_is_sanitized_and_connection_closed(self):
        self.connection.recv.side_effect = websocket.WebSocketTimeoutException("wss://provider/?authorization=test-api-secret")
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertNotIn("authorization", str(caught.exception))
        self.assertNotIn("test-api-secret", str(caught.exception))
        self.connection.close.assert_called_once()

    def test_total_deadline_stops_a_stream_that_never_finishes(self):
        self.connection.recv.return_value = packet("继续观察", 1)
        # Start at 0, four short successful reads, then budget expires before a fifth.
        with patch.object(vision.time, "monotonic", side_effect=[0, 10, 20, 30, 40, 50]):
            with self.assertRaises(vision.VisionError) as caught:
                vision.understand_image(b"image", "看看")
        self.assertIn("超时", str(caught.exception))
        self.assertEqual(self.connection.recv.call_count, 4)
        self.assertEqual([c.args[0] for c in self.connection.settimeout.call_args_list], [15, 15, 15, 5])
        self.connection.close.assert_called_once()

    def test_expired_budget_before_first_read_closes_socket(self):
        with patch.object(vision.time, "monotonic", side_effect=[0, 46]):
            with self.assertRaises(vision.VisionError):
                vision.understand_image(b"image", "看看")
        self.connection.recv.assert_not_called()
        self.connection.close.assert_called_once()

    def test_connection_failure_is_sanitized(self):
        self.connect.side_effect = OSError("signed URL authorization=test-api-secret")
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertNotIn("authorization", str(caught.exception))
        self.assertNotIn("test-api-secret", str(caught.exception))
        self.connection.close.assert_not_called()

    def test_send_failure_still_closes_socket(self):
        self.connection.send.side_effect = OSError("test-api-secret")
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertNotIn("test-api-secret", str(caught.exception))
        self.connection.close.assert_called_once()

    def test_malformed_provider_packet_is_sanitized(self):
        for raw in ["not-json test-api-secret", '{"header":{"code":0}}', packet(["not a string"]), '{"header":{"code":0},"payload":{"choices":{"status":2,"text":[]}}}']:
            with self.subTest(raw=raw):
                self.connection.reset_mock()
                self.connection.recv.side_effect = None
                self.connection.recv.return_value = raw
                with self.assertRaises(vision.VisionError) as caught:
                    vision.understand_image(b"image", "看看")
                self.assertNotIn("test-api-secret", str(caught.exception))
                self.connection.close.assert_called_once()

    def test_oversize_provider_text_fails_closed(self):
        self.connection.recv.return_value = packet("麦" * 20001, 2)
        with self.assertRaises(vision.VisionError) as caught:
            vision.understand_image(b"image", "看看")
        self.assertIn("异常", str(caught.exception))
        self.connection.close.assert_called_once()

    def test_close_failure_does_not_destroy_completed_observation(self):
        self.connection.recv.return_value = packet("图片观察")
        self.connection.close.side_effect = OSError("close error")
        self.assertEqual(vision.understand_image(b"image", "看看"), "图片观察")

    def test_missing_vision_configuration_does_not_open_socket(self):
        with patch.object(config, "XFYUN_API_SECRET", ""):
            with self.assertRaises(vision.VisionError) as caught:
                vision.understand_image(b"image", "看看")
        self.connect.assert_not_called()
        self.assertIn("配置", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
