import json
import unittest

from response_stream import stream_response
from test_answer_review import checked


class ResponseStreamTests(unittest.TestCase):
    def test_checked_content_arrives_before_upstream_finishes(self):
        finished = []
        frame = checked('第一段。第二段。')
        boundary = frame.index('第二段')
        def upstream():
            yield frame[:boundary]
            finished.append(True)
            yield frame[boundary:]
        stream = stream_response(upstream(), require_checks=True)
        self.assertEqual(next(stream)['type'], 'answer_review')
        first = next(stream)
        self.assertEqual(first, {'type':'answer_delta', 'content':'第一段。'})
        self.assertFalse(finished, 'must not collect upstream before yielding text')
        remaining = list(stream)
        self.assertEqual(remaining[-1]['content'], '第一段。第二段。')

    def test_split_escapes_and_surrogates_are_decoded_without_exposing_json(self):
        text = '中文\n"引号"\\路径🌾'
        frame = json.dumps({'action':'answer','content':text}, ensure_ascii=True)
        for split in range(1, len(frame)):
            with self.subTest(split=split):
                events = list(stream_response(iter([frame[:split], frame[split:]])))
                self.assertEqual(''.join(e['content'] for e in events if e['type']=='answer_delta'), text)
                self.assertEqual(events[-1]['content'], text)

    def test_tool_json_is_never_exposed_as_text(self):
        frame = json.dumps(dict(action='tool', tool='get_weather', args={'location':'郑州'}), ensure_ascii=False)
        events = list(stream_response(iter(frame), require_checks=True))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['data']['tool'], 'get_weather')

    def test_partial_or_duplicate_json_never_finishes(self):
        for raw in ['{"action":"answer","content":"半截', '{"action":"answer","content":"正文","action":"tool"}', '{"action":"answer","content":"正文","unknown":true}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                list(stream_response(iter(raw)))

    def test_disconnect_closes_upstream_generator(self):
        closed = []
        def upstream():
            try:
                yield '第一段'
                yield '第二段'
            finally:
                closed.append(True)
        stream = stream_response(upstream())
        next(stream)
        stream.close()
        self.assertEqual(closed, [True])


if __name__ == '__main__': unittest.main()
