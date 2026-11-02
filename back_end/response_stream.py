"""Separate private tool JSON from incremental, checked user-facing text.

The content field must be last. Decode only complete JSON string characters;
never expose tool arguments, reasoning, control metadata or broken escapes.
"""
import json

from answer_review import AnswerHeader


class ResponseFormatError(ValueError):
    """Model output could not be validated; safe to classify without raw text."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response field")
        result[key] = value
    return result


DECODER = json.JSONDecoder(object_pairs_hook=unique_object)


def content_prefix(text):
    """Return complete root fields before content and its string start, if ready."""
    pos = 1
    fields = {}
    while True:
        try:
            while pos < len(text) and text[pos].isspace():
                pos += 1
            key, pos = DECODER.raw_decode(text, pos)
            if not isinstance(key, str) or key in fields:
                raise ValueError("invalid response key")
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text):
                return None
            if text[pos] != ":":
                raise ValueError("missing colon")
            pos += 1
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text):
                return None
            if key == "content":
                if text[pos] != '"':
                    raise ValueError("content must be text")
                return fields, pos + 1
            # Wait for the delimiter too: a partial scalar 'tru' or '1' must
            # not be interpreted as a complete value before the next chunk.
            value, end = DECODER.raw_decode(text, pos)
            while end < len(text) and text[end].isspace():
                end += 1
            if end >= len(text):
                return None
            fields[key] = value
            if text[end] == "}":
                return None  # tool frame or object without content
            if text[end] != ",":
                raise ValueError("invalid field delimiter")
            pos = end + 1
        except json.JSONDecodeError:
            return None


def string_prefix(text, start):
    """Decode only a complete prefix, retaining split escapes/surrogate pairs."""
    pos = start
    while pos < len(text):
        char = text[pos]
        if char == '"':
            break
        if ord(char) < 32:
            raise ValueError("unescaped control character")
        if char == "\\":
            if pos + 1 >= len(text):
                break
            if text[pos + 1] == "u":
                if pos + 6 > len(text):
                    break
                code = int(text[pos + 2:pos + 6], 16)
                if 0xD800 <= code <= 0xDBFF:
                    if pos + 12 > len(text):
                        break
                    if text[pos + 6:pos + 8] != "\\u" or not 0xDC00 <= int(text[pos + 8:pos + 12], 16) <= 0xDFFF:
                        raise ValueError("unpaired unicode surrogate")
                    pos += 12
                    continue
                if 0xDC00 <= code <= 0xDFFF:
                    raise ValueError("unpaired unicode surrogate")
                pos += 6
                continue
            if text[pos + 1] not in '"\\/bfnrt':
                raise ValueError("invalid escape")
            pos += 2
            continue
        pos += 1
    return json.loads('"' + text[start:pos] + '"')


TOOL_OPEN = '<tool_call>'
TOOL_CLOSE = '</tool_call>'
PRIVATE_STARTS = (TOOL_OPEN, '<tool_calls>', '<function_call>', '<function=', TOOL_CLOSE, '<think>', '<analysis>')


def is_control_envelope(text):
    return isinstance(text,str) and text.lstrip().lower().startswith(('<tool','</tool','<function','<think','<analysis'))


def wrapped_tool(text):
    """Accept one complete canonical tool object, never recover arbitrary text.

    Some model endpoints emit an opening marker without a closing marker. A
    complete JSON object and normal upstream completion are still mandatory.
    """
    payload=text[len(TOOL_OPEN):].lstrip()
    data,end=DECODER.raw_decode(payload)
    tail=payload[end:].strip()
    if tail.lower() not in ('',TOOL_CLOSE):raise ValueError('invalid tool envelope')
    if (not isinstance(data,dict) or data.get('action')!='tool'
            or set(data)-{'action','tool','args'} or not isinstance(data.get('tool'),str)
            or not data['tool'] or not isinstance(data.get('args',{}),dict)):
        raise ValueError('invalid tool envelope')
    data.setdefault('args',{})
    return data


def stream_response(chunks, *, require_checks=False):
    buffer, mode, emitted, prefix = "", None, "", None
    header = None
    try:
        for chunk in chunks:
            if not isinstance(chunk, str):
                raise ValueError("invalid model chunk")
            buffer += chunk
            if len(buffer) > 24000:
                raise ValueError("response too long")
            text = buffer.lstrip()
            if not text:
                continue
            if mode is None:
                # Wait when a private marker is split across network chunks.
                if any(marker.startswith(text.lower()) for marker in PRIVATE_STARTS):
                    continue
                if text.lower().startswith(TOOL_OPEN):mode='wrapped_tool'
                elif text.lower().startswith(('<tool','</tool','<function','<think','<analysis')):
                    raise ValueError('unsupported tool envelope')
                else:mode = "json" if text[0] == "{" else "text"
                if require_checks and mode == "text":
                    raise ValueError("missing evidence header")
            if mode == 'wrapped_tool':
                continue  # Buffer private parameters until the entire object validates.
            if mode == "text":
                # Plain responses cannot expose markdown-fenced control JSON.
                if text.startswith("`"):
                    raise ValueError("unexpected fenced response")
                value = text
            else:
                if prefix is None:
                    prefix = content_prefix(text)
                    if prefix is None:
                        continue
                    fields, _ = prefix
                    if require_checks or "checks" in fields:
                        header = AnswerHeader.model_validate(fields).ensure_supported()
                        yield {"type": "answer_review", "status": header.verdict, "issue_codes": header.issue_codes}
                    elif fields != {"action": "answer"}:
                        raise ValueError("invalid answer header")
                value = string_prefix(text, prefix[1])
            delta = value[len(emitted):]
            if delta:
                emitted = value
                yield {"type": "answer_delta", "content": delta}
        if mode == 'wrapped_tool':
            data=wrapped_tool(buffer.lstrip())
            yield {'type':'model_result','data':data,'content':json.dumps(data,ensure_ascii=False)}
            return
        if mode is None and buffer.lstrip().startswith('<'):
            raise ValueError('incomplete tool envelope')
        if mode == "json":
            data = json.loads(buffer, object_pairs_hook=unique_object)
            if not isinstance(data, dict):
                raise ValueError("invalid frame")
            if data.get("action") == "tool" and not emitted and prefix is None:
                yield {"type": "model_result", "data": data, "content": buffer}
                return
            final = data.pop("content", None)
            if not isinstance(final, str) or not final.strip() or final != emitted:
                raise ValueError("incomplete answer")
            if header is not None:
                if data != header.model_dump():
                    raise ValueError("changed answer metadata")
            elif data != {"action": "answer"}:
                raise ValueError("unexpected answer field")
        else:
            final = emitted
        if not final or not final.strip():
            raise ValueError("empty model response")
        yield {"type": "model_result", "data": None, "content": final}
    except ValueError as exc:
        raise ResponseFormatError("invalid answer format or evidence checks") from exc
    finally:
        close = getattr(chunks, "close", None)
        if close:
            close()
