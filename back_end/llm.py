import json

import requests

import config


class LLMError(Exception):
    """大模型调用失败时抛出。"""


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
    except requests.RequestException as exc:
        raise LLMError(f"请求大模型接口失败：{exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"大模型接口返回 {resp.status_code}：{resp.text}")

    # 讯飞接口返回 UTF-8，但 Content-Type 未声明 charset 时 requests 可能猜成
    # ISO-8859-1，导致中文乱码，这里显式指定编码。
    resp.encoding = "utf-8"
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"解析大模型响应失败：{data}") from exc


def chat_stream(messages: list[dict]):
    """流式调用大模型，逐段 yield 增量文本（delta content）。"""
    if not config.SPARK_API_PASSWORD:
        raise LLMError("未配置 SPARK_API_PASSWORD，请在 .env 中填写讯飞星火的 APIPassword。")

    try:
        resp = requests.post(
            _url(), json=_payload(messages, stream=True), headers=_headers(),
            timeout=60, stream=True,
        )
    except requests.RequestException as exc:
        raise LLMError(f"请求大模型接口失败：{exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"大模型接口返回 {resp.status_code}：{resp.text}")

    # 上游是 text/event-stream 且不带 charset，requests 会默认按 ISO-8859-1 解码，
    # 中文就变成「ä½ å¥½」式乱码。这里直接读原始字节，显式用 UTF-8 解码。
    resp.encoding = "utf-8"
    try:
        for raw in resp.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content", "")
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                continue
            if delta:
                yield delta
    except requests.RequestException as exc:
        raise LLMError(f"流式响应中断：{exc}") from exc
