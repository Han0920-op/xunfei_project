import json
import unittest
from unittest.mock import patch, Mock

import config
import llm


def frame(delta=None, **kwargs):
    return ('data: '+json.dumps({'choices':[{'delta':delta or {}, **kwargs}]}, ensure_ascii=False)).encode()


class LLMStreamTests(unittest.TestCase):
    def response(self, lines, status=200):
        response = Mock(status_code=status)
        response.iter_lines.return_value = iter(lines)
        return response

    def test_real_stream_flag_tiny_chunks_reasoning_hidden_and_cleanup(self):
        response = self.response([frame({'reasoning_content':'内部思考', 'content':None}), frame({'content':'你好'}), frame({'content':None}, finish_reason='stop'), b'data: [DONE]'])
        with patch.object(config, 'SPARK_API_PASSWORD', 'test-only'), patch.object(llm.requests, 'post', return_value=response) as post:
            self.assertEqual(list(llm.chat_stream([])), ['你好'])
        self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertTrue(post.call_args.kwargs['stream'])
        response.iter_lines.assert_called_once_with(chunk_size=1, decode_unicode=False)
        response.close.assert_called_once()

    def test_truncation_missing_done_malformed_and_provider_errors_fail_closed(self):
        cases = [[frame({'content':'部分'})], [frame(finish_reason='length'), b'data: [DONE]'], [b'data: invalid-json'], [b'data: {"error":{"message":"private"}}']]
        for lines in cases:
            response = self.response(lines)
            with self.subTest(lines=lines), patch.object(config, 'SPARK_API_PASSWORD', 'test'), patch.object(llm.requests, 'post', return_value=response), self.assertRaises(llm.LLMError):
                list(llm.chat_stream([]))
            response.close.assert_called_once()

    def test_cancelling_stream_closes_response_and_non_200_closes_response(self):
        for status in [200, 401]:
            response = self.response([frame({'content':'第一段'}), frame({'content':'第二段'}), b'data: [DONE]'], status)
            with patch.object(config, 'SPARK_API_PASSWORD', 'test'), patch.object(llm.requests, 'post', return_value=response):
                stream = llm.chat_stream([])
                if status == 200:
                    self.assertEqual(next(stream), '第一段')
                    stream.close()
                else:
                    with self.assertRaises(llm.LLMError): list(stream)
            response.close.assert_called_once()


if __name__ == '__main__': unittest.main()
