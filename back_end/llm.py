import json
import time

import requests

import config


class LLMError(Exception):
    """大模型调用失败时抛出。"""

    def __init__(self, message, code="model_request_failed"):
        super().__init__(message)
        self.code = code


def http_error(status):
    code = {401: "model_auth_failed", 403: "model_auth_failed",
            404: "model_endpoint_invalid", 400: "model_request_invalid",
            422: "model_request_invalid", 429: "model_rate_limited"}.get(
                status, "model_unavailable" if status >= 500 else "model_request_failed")
    error = LLMError(f"模型接口 HTTP {status}", code)
    error.status_code = status
    return error


def _url() -> str:
    return f"{config.SPARK_BASE_URL.rstrip('/')}/chat/completions"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.SPARK_API_PASSWORD}",
        "Content-Type": "application/json",
    }


def _payload(messages: list[dict], stream: bool = False) -> dict:
    payload = {
        "model": config.SPARK_MODEL,
        "messages": messages,
        "temperature": config.SPARK_TEMPERATURE,
        "max_tokens": config.SPARK_MAX_TOKENS,
    }
    if stream:
        payload["stream"] = True
    return payload


def chat(messages: list[dict]) -> str:
    if not config.SPARK_API_PASSWORD:
        raise LLMError("未配置 SPARK_API_PASSWORD，请在 .env 中填写讯飞星火的 APIPassword。")

    try:
        resp = requests.post(
            _url(), json=_payload(messages), headers=_headers(), timeout=60
        )
    except requests.Timeout as exc:
        raise LLMError("模型连接超时", "model_timeout") from exc
    except requests.RequestException as exc:
        raise LLMError("模型连接失败", "model_connection_failed") from exc

    if resp.status_code != 200:
        raise http_error(resp.status_code)

    # 讯飞接口返回 UTF-8，但 Content-Type 未声明 charset 时 requests 可能猜成
    # ISO-8859-1，导致中文乱码，这里显式指定编码。
    resp.encoding = "utf-8"
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("解析模型响应失败", "model_stream_invalid") from exc


def chat_stream(messages: list[dict], *, trace=None):
    """流式调用大模型，逐段 yield 增量文本（delta content）。"""
    if not config.SPARK_API_PASSWORD:
        raise LLMError("未配置 SPARK_API_PASSWORD，请在 .env 中填写讯飞星火的 APIPassword。")

    remaining = getattr(trace, "deadline", float("inf")) - time.monotonic()
    if remaining <= 0:
        raise LLMError("模型响应超时", "model_timeout")
    try:
        resp = requests.post(
            _url(), json=_payload(messages, stream=True), headers=_headers(),
            timeout=(min(5, remaining), min(45, remaining)), stream=True,
        )
    except requests.Timeout as exc:
        raise LLMError("模型连接超时", "model_timeout") from exc
    except requests.RequestException as exc:
        raise LLMError("模型连接失败", "model_connection_failed") from exc

    # 上游是 text/event-stream 且不带 charset，requests 会默认按 ISO-8859-1 解码，
    # 中文就变成「ä½ å¥½」式乱码。这里直接读原始字节，显式用 UTF-8 解码。
    resp.encoding = "utf-8"
    deadline = min(time.monotonic() + 120, getattr(trace,"deadline",float("inf")))
    finished = False
    try:
        if trace:
            trace.log("model.http_response", status_code=resp.status_code)
        if resp.status_code != 200:
            raise http_error(resp.status_code)
        # requests defaults to buffering 512 bytes, which delays small SSE events.
        for raw in resp.iter_lines(chunk_size=1, decode_unicode=False):
            if time.monotonic() > deadline:
                raise LLMError("模型响应超时", "model_timeout")
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                finished = True
                break
            try:
                event = json.loads(data)
                if not isinstance(event,dict):raise LLMError("模型流格式错误", "model_stream_invalid")
                # Xunfei can send a business failure with HTTP 200 and no choices.
                # Treat it as the original upstream failure, not an empty answer.
                if isinstance(event, dict) and event.get("code") not in (None, 0, "0"):
                    error = LLMError("模型服务返回业务错误", "model_request_failed")
                    value = event["code"]
                    if type(value) is int or isinstance(value, str) and value.isdecimal() and len(value) <= 6:
                        number = int(value)
                        if 0 <= number <= 999999:
                            error.provider_code = number
                            if trace: trace.log("model.provider_business_error", status_code=resp.status_code, provider_code=number)
                    raise error
                if event.get("error"):
                    error = LLMError("模型流返回错误")
                    provider_error = event["error"]
                    if isinstance(provider_error, dict) and type(provider_error.get("code")) is int:
                        error.provider_code = provider_error["code"]
                    raise error
                choices = event.get("choices", [])
                if not isinstance(choices,list):raise LLMError("模型流格式错误", "model_stream_invalid")
                if not choices:
                    continue  # optional usage-only frame
                choice = choices[0]
                if not isinstance(choice,dict) or not isinstance(choice.get("delta",{}),dict):raise LLMError("模型流格式错误", "model_stream_invalid")
                if choice.get("finish_reason") not in (None, "stop"):
                    error = LLMError("模型回答被截断或过滤", "model_truncated" if choice.get("finish_reason") == "length" else "model_filtered")
                    error.finish_reason = choice.get("finish_reason")
                    raise error
                # Never expose reasoning_content from reasoning models.
                delta = choice.get("delta", {}).get("content", "")
                if delta is None:
                    delta = ""  # initial/reasoning-only/finish frames may use null
                if not isinstance(delta, str):
                    raise LLMError("模型流格式错误", "model_stream_invalid")
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise LLMError("模型流格式错误", "model_stream_invalid") from exc
            if delta:
                yield delta
        if not finished:
            raise LLMError("模型流中断，未取得完成标识", "model_stream_interrupted")
    except requests.Timeout as exc:
        raise LLMError("模型响应超时", "model_timeout") from exc
    except requests.RequestException as exc:
        raise LLMError("模型流式响应中断", "model_stream_interrupted") from exc
    finally:
        resp.close()
