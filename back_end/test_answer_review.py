"""Evidence guards remain in the streamed generation; no serial full-answer review."""
import json
import unittest
from unittest.mock import patch

import config
import dialogue
from response_stream import stream_response

CHECKS = dict(temporal_consistency=True, current_image_priority=True,
              health_claim_supported=True, action_supported=True)


def checked(text, **changes):
    frame = dict(action='answer', verdict='supported', checks=CHECKS, issue_codes=[], content=text)
    frame.update(changes)
    return json.dumps(frame, ensure_ascii=False)


class EvidenceStreamTests(unittest.TestCase):
    def test_current_image_excludes_past_assistant_conclusion_and_uses_one_call(self):
        history = [dict(role='user', content='帮我看看旧图'), dict(role='assistant', content='【此前该轮图片的初步观察，非本轮新识别】金黄麦穗\n【此前回答】10月正常收获，立即收获。')]
        answer = '这张图呈幼苗状，叶片黄化不能按成熟衰老处理。照片是什么时候拍的？'

        def model(messages):
            all_text = json.dumps(messages, ensure_ascii=False)
            self.assertNotIn('10月正常收获，立即收获', all_text)
            self.assertIn('金黄麦穗', all_text)
            self.assertIn('幼苗状叶片发黄', all_text)
            self.assertIn('不是照片拍摄时间', all_text)
            self.assertIn('秋季一般是播种出苗', all_text)
            return iter(checked(answer, verdict='revised', issue_codes=['history_conflict']))

        with patch.object(config, 'SPARK_API_PASSWORD', 'test-only'), patch.object(dialogue, 'understand_image', return_value='幼苗状叶片发黄，穗部未能辨认'), patch.object(dialogue.llm, 'chat_stream', side_effect=model) as model_call:
            events = list(dialogue.run_turn('这张是新的照片', history, b'test photo'))
        self.assertEqual(model_call.call_count, 1)
        self.assertEqual(''.join(e['content'] for e in events if e['type']=='answer_delta'), answer)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertTrue(any(e['type']=='answer_review' and e['status']=='revised' for e in events))

    def test_bad_check_or_missing_checks_cannot_emit_body(self):
        for raw in [checked('立即收获', checks={**CHECKS, 'action_supported':False}), checked('立即收获', checks={**CHECKS, 'action_supported':'true'}), '现在正常成熟，立即收获。', '{"action":"answer","content":"立即收获"}']:
            events = []
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                for event in stream_response(iter(raw), require_checks=True):
                    events.append(event)
            self.assertFalse(any(e['type']=='answer_delta' for e in events))

    def test_photo_failure_notice_remains_in_stream_and_final(self):
        with patch.object(config, 'SPARK_API_PASSWORD', 'test-only'), patch.object(dialogue, 'understand_image', side_effect=RuntimeError('private')), patch.object(dialogue.llm, 'chat_stream', return_value=iter(checked('暂不能确定原因，请描述异常。', verdict='insufficient'))):
            events = list(dialogue.run_turn('叶片黄化', [], b'photo'))
        final = next(e['content'] for e in events if e['type']=='answer')
        self.assertTrue(final.startswith('这张照片尚未完成识别'))
        self.assertEqual(final, ''.join(e['content'] for e in events if e['type']=='answer_delta'))
        self.assertNotIn('private', json.dumps(events))


if __name__ == '__main__': unittest.main()
