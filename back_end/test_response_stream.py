import json
import unittest

from response_stream import stream_response
from test_answer_review import checked


class ResponseStreamTests(unittest.TestCase):
    def test_checked_content_arrives_before_upstream_finishes(self):
        finished = []
        frame = checked("第一段。第二段。")
        boundary = frame.index("第二段")

        def upstream():
            yield frame[:boundary]
            finished.append(True)
            yield frame[boundary:]

        stream = stream_response(upstream(), require_checks=True)
        self.assertEqual(next(stream)["type"], "answer_review")
        first = next(stream)
        self.assertEqual(first, {"type": "answer_delta", "content": "第一段。"})
        self.assertFalse(finished, "must not collect upstream before yielding text")
        remaining = list(stream)
        self.assertEqual(remaining[-1]["content"], "第一段。第二段。")

    def test_split_escapes_and_surrogates_are_decoded_without_exposing_json(self):
        text = '中文\n"引号"\\路径🌾'
        frame = json.dumps({"action": "answer", "content": text}, ensure_ascii=True)
        for split in range(1, len(frame)):
            with self.subTest(split=split):
                events = list(stream_response(iter([frame[:split], frame[split:]])))
                self.assertEqual(
                    "".join(
                        e["content"] for e in events if e["type"] == "answer_delta"
                    ),
                    text,
                )
                self.assertEqual(events[-1]["content"], text)

    def test_tool_json_is_never_exposed_as_text(self):
        frame = json.dumps(
            dict(action="tool", tool="get_weather", args={"location": "郑州"}),
            ensure_ascii=False,
        )
        events = list(stream_response(iter(frame), require_checks=True))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"]["tool"], "get_weather")

    def test_partial_or_duplicate_json_never_finishes(self):
        for raw in [
            '{"action":"answer","content":"半截',
            '{"action":"answer","content":"正文","action":"tool"}',
            '{"action":"answer","content":"正文","unknown":true}',
        ]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                list(stream_response(iter(raw)))

    def test_tagged_tool_call_is_private_for_every_split_with_or_without_closing_tag(
        self,
    ):
        frame = json.dumps(
            {
                "action": "tool",
                "tool": "prepare_reminder",
                "args": {
                    "name": "检查农作物",
                    "concern": "记录变化",
                    "recurrence": "once",
                    "run_at": "2026-11-02T20:00",
                },
            },
            ensure_ascii=False,
        )
        for ending in ("", "</tool_call>"):
            raw = "<tool_call>" + frame + ending
            for split in range(1, len(raw)):
                with self.subTest(ending=ending, split=split):
                    events = list(
                        stream_response(
                            iter([raw[:split], raw[split:]]), require_checks=True
                        )
                    )
                    self.assertEqual([e["type"] for e in events], ["model_result"])
                    self.assertEqual(events[0]["data"]["tool"], "prepare_reminder")
                    self.assertNotIn("<tool_call>", events[0]["content"])
            self.assertEqual(len(list(stream_response(iter(raw)))), 1)

    def test_wrapper_tokens_inside_arguments_are_data_and_case_insensitive_tags_work(
        self,
    ):
        data = {
            "action": "tool",
            "tool": "prepare_reminder",
            "args": {"concern": "检查文字</tool_call>不能执行", "name": "提醒"},
        }
        events = list(
            stream_response(
                iter(
                    [
                        "<TOOL_CALL>"
                        + json.dumps(data, ensure_ascii=False)
                        + "</TOOL_CALL>"
                    ]
                )
            )
        )
        self.assertEqual(events[0]["data"], data)

    def test_malformed_multiple_or_unsupported_private_frames_never_expose_any_delta(
        self,
    ):
        tool = '{"action":"tool","tool":"prepare_reminder","args":{}}'
        samples = [
            "<tool_call>",
            '<tool_call>{"action":"tool"',
            "<tool_call>" + tool + "</tool_ca",
            "<tool_call>" + tool + "</tool_call>以及其他文本",
            "<tool_call>" + tool + "</tool_call><tool_call>" + tool + "</tool_call>",
            '<tool_call>{"action":"answer","content":"private"}</tool_call>',
            '<tool_call>{"action":"tool","tool":"x","tool":"y","args":{}}</tool_call>',
            "<function_call>" + tool + "</function_call>",
            "<think>private reasoning</think>",
            "<tool_call extra>" + tool,
        ]
        for raw in samples:
            events = []
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                for e in stream_response(iter(raw)):
                    events.append(e)
            self.assertEqual(events, [])

    def test_tagged_tool_is_not_executed_before_upstream_success_and_closes_on_error(
        self,
    ):
        import llm

        closed = []
        events = []

        def upstream():
            try:
                yield '<tool_call>{"action":"tool","tool":"prepare_reminder","args":{}}'
                raise llm.LLMError("模型流中断", "model_stream_interrupted")
            finally:
                closed.append(True)

        with self.assertRaises(llm.LLMError):
            for e in stream_response(upstream()):
                events.append(e)
        self.assertEqual(events, [])
        self.assertEqual(closed, [True])

    def test_plain_non_control_angle_text_keeps_real_streaming(self):
        events = list(stream_response(iter(["<", " 3是比较表达式"])))
        self.assertEqual(
            "".join(e["content"] for e in events if e["type"] == "answer_delta"),
            "< 3是比较表达式",
        )

    def test_disconnect_closes_upstream_generator(self):
        closed = []

        def upstream():
            try:
                yield "第一段"
                yield "第二段"
            finally:
                closed.append(True)

        stream = stream_response(upstream())
        next(stream)
        stream.close()
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
