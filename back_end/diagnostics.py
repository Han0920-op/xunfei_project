"""Allowlisted diagnostic metadata only; never format exception values or locals.

Exception messages, repr(), response bodies, URLs, model text, inputs and images
are deliberately excluded. Follow causes/contexts to identify swallowed errors.
"""
import json
import logging
import re
import time
import uuid
from pathlib import Path

from pydantic import ValidationError

LOGGER = logging.getLogger('uvicorn.error')
FILES = {'chat_api.py', 'dialogue.py', 'llm.py', 'response_stream.py', 'answer_review.py',
         'tools.py', 'weather.py', 'knowledge.py', 'pesticides.py', 'vision.py'}
TYPES = {'Exception', 'RuntimeError', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
         'AttributeError', 'JSONDecodeError', 'ValidationError', 'ResponseFormatError',
         'LLMError', 'VisionError', 'Timeout', 'ReadTimeout', 'ConnectTimeout',
         'ConnectionError', 'ProxyError', 'SSLError', 'HTTPError', 'ChunkedEncodingError',
         'ReadTimeoutError', 'ProtocolError', 'NewConnectionError', 'MaxRetryError',
         'WebSocketTimeoutException', 'WebSocketConnectionClosedException', 'WebSocketBadStatusException',
         'ZoneInfoNotFoundError', 'FileNotFoundError', 'PermissionError'}
# Exact messages from our own raise sites; all other strings remain private.
REASONS = {'missing evidence header': 'missing_evidence_header',
           'unexpected fenced response': 'fenced_response',
           'evidence checks incomplete': 'evidence_checks_incomplete',
           'duplicate response field': 'duplicate_response_field',
           'invalid answer header': 'invalid_answer_header',
           'changed answer metadata': 'changed_answer_metadata',
           'incomplete answer': 'incomplete_answer',
           'empty model response': 'empty_model_response',
           'response too long': 'response_too_long',
           'invalid escape': 'invalid_json_escape',
           'unescaped control character': 'unescaped_control_character',
           '模型流中断，未取得完成标识': 'missing_done',
           '模型回答被截断或过滤': 'non_stop_finish',
           '模型流格式错误': 'invalid_sse_frame',
           '模型流返回错误': 'provider_error_frame'}
FIELDS = {'action', 'verdict', 'checks', 'temporal_consistency', 'current_image_priority',
          'health_claim_supported', 'action_supported', 'issue_codes', 'content'}
VALIDATION_TYPES = {'missing', 'extra_forbidden', 'bool_type', 'literal_error', 'list_type',
                    'string_type', 'model_type', 'too_long'}


def exception_metadata(exc):
    chain, visited = [], set()
    while exc is not None and id(exc) not in visited and len(chain) < 6:
        visited.add(id(exc))
        name = type(exc).__name__
        item = {'type': name if name in TYPES else 'OtherException'}
        frames = []
        tb = exc.__traceback__
        while tb:
            filename = Path(tb.tb_frame.f_code.co_filename).name
            if filename in FILES:
                frames.append({'file': filename, 'line': tb.tb_lineno})
            tb = tb.tb_next
        item['frames'] = frames[-8:]
        # Do not call str(exc): validation/network exceptions often embed data.
        if type(exc) is ValueError or name == 'LLMError':
            if len(exc.args) == 1 and isinstance(exc.args[0], str):
                reason = REASONS.get(exc.args[0])
                if reason:
                    item['reason'] = reason
        if isinstance(exc, ValidationError):
            item['validation'] = [
                {'type': e['type'] if e['type'] in VALIDATION_TYPES else 'other',
                 'fields': [part if part in FIELDS else '<other>' for part in e['loc'] if isinstance(part, str)]}
                for e in exc.errors(include_url=False, include_context=False, include_input=False)[:10]
            ]
        if isinstance(exc, json.JSONDecodeError):
            item['json_line'], item['json_column'] = exc.lineno, exc.colno
        for attr in ('status_code', 'provider_code'):
            value = getattr(exc, attr, None)
            if type(value) is int and 0 <= value <= 999999:
                item[attr] = value
        finish = getattr(exc, 'finish_reason', None)
        if finish in ('length', 'content_filter', 'stop', 'tool_calls'):
            item['finish_reason'] = finish
        chain.append(item)
        exc = exc.__cause__ if exc.__cause__ is not None else exc.__context__
    return chain


class Trace:
    def __init__(self, request_id=None):
        self.request_id = request_id if isinstance(request_id, str) and re.fullmatch('[a-f0-9]{12}', request_id) else uuid.uuid4().hex[:12]
        self.started = time.monotonic()

    def log(self, stage, *, exc=None, **counts):
        record = {'event': 'chat_diagnostic', 'request_id': self.request_id,
                  'stage': stage, 'elapsed_ms': round((time.monotonic()-self.started)*1000)}
        if counts.get('tool') in ('get_weather', 'search_knowledge', 'check_pesticide', 'get_soil'):
            record['tool'] = counts['tool']
        # Only bounded primitive counters/flags are accepted. No arbitrary text.
        for key in ('history_messages', 'context_messages', 'has_image', 'requires_checks',
                    'tool_round', 'model_calls', 'upstream_content_chunks', 'status_code', 'provider_code'):
            value = counts.get(key)
            if type(value) in (int, bool) and 0 <= value <= 1000000:
                record[key] = value
        if exc is not None:
            record['exceptions'] = exception_metadata(exc)
        LOGGER.log(logging.WARNING if exc is not None else logging.INFO,
                   'chat_diagnostic %s', json.dumps(record, ensure_ascii=True))
