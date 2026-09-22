import requests

import config


class LLMError(Exception):
    """大模型调用失败时抛出。"""


def chat(messages: list[dict]) -> str:
    if not config.SPARK_API_PASSWORD:
        raise LLMError("未配置 SPARK_API_PASSWORD，请在 .env 中填写讯飞星火的 APIPassword。")

    url = f"{config.SPARK_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.SPARK_API_PASSWORD}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.SPARK_MODEL,
        "messages": messages,
        "temperature": config.SPARK_TEMPERATURE,
        "max_tokens": config.SPARK_MAX_TOKENS,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise LLMError(f"请求大模型接口失败：{exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"大模型接口返回 {resp.status_code}：{resp.text}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"解析大模型响应失败：{data}") from exc
