"""Reproduce SSE failures without secrets, real photos or paid requests."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import config
import dialogue
import tools
import llm
from diagnostics import Trace, exception_metadata
from main import app
from runtime import STREAM_PROTOCOL
from test_dialogue import checked, sse, answers


class DiagnosticTests(unittest.TestCase):
    def test_provider_code_11200_reproduces_empty_response_chain(self):
        # Observed provider frame shape, with a synthetic private message.
        response = Mock(status_code=200)
        response.iter_lines.return_value = iter([
            b'data: {"code":11200,"message":"private-provider-detail"}', b'data: [DONE]'])
        with patch.object(config,'SPARK_API_PASSWORD','test'), patch.object(llm.requests,'post',return_value=response), self.assertLogs('uvicorn.error',level='INFO') as logs:
            result = self.post()
        self.assertEqual(result.status_code,200)
        self.assertEqual(sse(result)[-1]['code'],'answer_format_invalid')
        records = self.records(logs)
        provider = next(r for r in records if r['stage']=='model.provider_business_error')
        self.assertEqual(provider['provider_code'],11200)
        failure = next(r for r in records if r['stage']=='agent.answer_validation_failed')
        self.assertEqual(failure['exceptions'][-1]['reason'],'empty_model_response')
        self.assertEqual(failure['request_id'],provider['request_id'])
        self.assertNotIn('private-provider-detail',''.join(logs.output))

    def post(self, history=None):
        return TestClient(app).post('/api/agent/chat', headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL},
            data={'message':'private-input-not-for-logs', 'history':json.dumps(history or [])})

    def records(self, logs):
        return [json.loads(line.split('chat_diagnostic ',1)[1]) for line in logs.output if 'chat_diagnostic ' in line]

    def test_multiturn_photo_history_activates_checks_without_current_photo(self):
        history = [{'role':'assistant','content':'【此前该轮图片的初步观察，非本轮新识别，未确诊】私人照片观察【此前回答】旧回答'}]
        with patch.object(config,'SPARK_API_PASSWORD','private-key'), patch.object(dialogue.llm,'chat_stream',side_effect=lambda _, **kwargs:iter(['plain-private-answer'])), self.assertLogs('uvicorn.error',level='INFO') as logs:
            plain = self.post()
            photo_history = self.post(history)
        self.assertEqual(sse(plain)[-1]['type'],'done')
        events = sse(photo_history)
        self.assertEqual(photo_history.status_code,200)
        self.assertEqual(events[-1]['code'],'answer_format_invalid')
        request_id = photo_history.headers['x-request-id']
        self.assertEqual(request_id,events[0]['request_id'])
        self.assertEqual(request_id,events[-1]['request_id'])
        records = [r for r in self.records(logs) if r['request_id']==request_id]
        self.assertTrue(next(r for r in records if r['stage']=='agent.context_ready')['requires_checks'])
        failure = next(r for r in records if r['stage']=='agent.answer_validation_failed')
        self.assertEqual(failure['exceptions'][-1]['type'],'ValueError')
        self.assertEqual(failure['exceptions'][-1]['reason'],'missing_evidence_header')
        self.assertEqual(failure['exceptions'][-1]['frames'][-1]['file'],'response_stream.py')
        for private in ['private-key','plain-private-answer','private-input-not-for-logs','私人照片观察','旧回答']:
            self.assertNotIn(private,''.join(logs.output))
        with patch.object(config,'SPARK_API_PASSWORD','test'), patch.object(dialogue.llm,'chat_stream',side_effect=lambda _, **kwargs:iter([checked('证据不足，请补近景。')])):
            repaired = self.post(history)
        self.assertEqual(sse(repaired)[-1]['type'],'done')

    def test_upstream_http_error_is_distinct_from_outer_http_200(self):
        response = Mock(status_code=401,text='private-provider-body')
        with patch.object(config,'SPARK_API_PASSWORD','private-key'), patch.object(llm.requests,'post',return_value=response), self.assertLogs('uvicorn.error',level='INFO') as logs:
            result = self.post()
        self.assertEqual(result.status_code,200)
        self.assertEqual(sse(result)[-1]['code'],'model_auth_failed')
        failure = next(r for r in self.records(logs) if r['stage']=='model.stream_failed')
        self.assertEqual(failure['exceptions'][0]['status_code'],401)
        self.assertNotIn('private-provider-body',''.join(logs.output))
        response.close.assert_called_once()

    def test_tool_failure_retains_original_type_and_can_still_answer(self):
        call = json.dumps({'action':'tool','tool':'search_knowledge','args':{'query':'private query'}})
        with patch.object(config,'SPARK_API_PASSWORD','test'), patch.object(dialogue.llm,'chat_stream',side_effect=[iter([call]),iter(['资料暂未取得，请补充近景。'])]), patch.object(tools.TOOLS['search_knowledge'],'func',side_effect=RuntimeError('private tool details')), self.assertLogs('uvicorn.error',level='INFO') as logs:
            result = self.post()
        self.assertEqual(sse(result)[-1]['type'],'done')
        self.assertTrue(answers(sse(result)))
        rows = self.records(logs)
        self.assertEqual(next(r for r in rows if r['stage']=='tool.execute_failed')['exceptions'][0]['type'],'RuntimeError')
        self.assertEqual([r['tool_round'] for r in rows if r['stage']=='model.start'],[0,1])
        self.assertNotIn('private tool details',''.join(logs.output))
        self.assertNotIn('private query',''.join(logs.output))

    def test_validation_does_not_leak_input_unknown_field_or_context(self):
        from answer_review import AnswerHeader
        private='secret-field-authorization'
        try:
            AnswerHeader.model_validate({private:'private-value'})
        except Exception as exc:
            metadata=exception_metadata(exc)
        encoded=json.dumps(metadata)
        self.assertNotIn(private,encoded)
        self.assertNotIn('private-value',encoded)
        self.assertIn('ValidationError',encoded)
        self.assertIn('missing',encoded)

    def test_exception_messages_and_source_lines_are_never_formatted(self):
        class HostileError(Exception):
            def __str__(self):
                raise AssertionError('exception string must not be read')
        try:
            try:
                raise llm.requests.ConnectionError('https://private/?api_key=secret')
            except Exception as cause:
                raise HostileError('private image bytes') from cause
        except Exception as exc:
            with self.assertLogs('uvicorn.error') as logs:
                Trace().log('test',exc=exc)
        self.assertIn('ConnectionError',''.join(logs.output))
        for private in ['https://private','secret','private image bytes','raise HostileError']:
            self.assertNotIn(private,''.join(logs.output))

    def test_generator_setup_failure_is_logged_and_emitted_with_request_id(self):
        with patch.object(config,'SPARK_API_PASSWORD','test'), patch.object(dialogue,'system_prompt',side_effect=RuntimeError('private config')), self.assertLogs('uvicorn.error') as logs:
            result = self.post()
        self.assertEqual(sse(result)[-1]['code'],'internal_error')
        self.assertIn('sse.generator_failed',''.join(logs.output))
        self.assertNotIn('private config',''.join(logs.output))

    def test_parallel_requests_do_not_share_ids(self):
        with patch.object(config,'SPARK_API_PASSWORD','test'), patch.object(dialogue.llm,'chat_stream',side_effect=lambda _, **kwargs:iter(['你好'])), self.assertLogs('uvicorn.error',level='INFO') as logs:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:self.post(), range(2)))
        ids={r.headers['x-request-id'] for r in results}
        self.assertEqual(len(ids),2)
        for response in results:
            self.assertEqual(sse(response)[0]['request_id'],response.headers['x-request-id'])
        self.assertEqual({r['request_id'] for r in self.records(logs)},ids)


if __name__=='__main__':
    unittest.main()
