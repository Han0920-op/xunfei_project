"""Safe local model-list probe. No prompt generation, raw errors, or secret output."""

import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1] / "back_end"
sys.path.insert(0, str(BACKEND))
import config
import llm
import requests


def model_id(value):
    return (
        value
        if isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_./:-]{1,120}", value)
        and not value.lower().startswith(("sk-", "bearer"))
        else "<invalid-or-redacted>"
    )


def probe():
    result = {"provider": config.text_provider()}
    if config.text_provider() not in ("deepseek", "qwen"):
        return {
            **result,
            "status": "provider_not_supported",
            "message": "请明确配置 LLM_PROVIDER=deepseek 或 qwen，保存 .env 并重启后端。",
        }
    settings = config.text_settings()
    result["model"] = model_id(settings["model"])
    if not settings["api_key"]:
        return {
            **result,
            "status": "model_not_configured",
            "message": "没有读取到所选供应商的 API Key。",
        }
    base = settings["base_url"].rstrip("/")
    try:
        url = urlsplit(base)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or base.endswith("/chat/completions")
        ):
            raise ValueError()
    except ValueError:
        return {
            **result,
            "status": "model_endpoint_invalid",
            "message": "请检查所选供应商的 BASE_URL，必须是 HTTPS 基础地址，不含 /chat/completions。",
        }
    result["api_host"] = url.hostname
    # Detect effective proxy use without exposing proxy URLs or credentials.
    result["proxy_configured"] = bool(requests.utils.get_environ_proxies(base))
    try:
        with requests.get(
            base + "/models",
            headers={"Authorization": "Bearer " + settings["api_key"]},
            timeout=(5, 15),
            stream=True,
            allow_redirects=False,
        ) as response:
            result["http_status"] = response.status_code
            if response.status_code != 200:
                code = llm.http_error(response.status_code).code
                return {
                    **result,
                    "status": code,
                    "message": "接口已返回 HTTP 响应。请检查授权、额度、地址或服务状态；404 也可能是服务不支持 /models，不能据此认定聊天模型不存在。",
                }
            chunks, size, deadline = [], 0, time.monotonic() + 20
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 1000000 or time.monotonic() > deadline:
                    raise ValueError()
                chunks.append(chunk)
            data = json.loads(b"".join(chunks))
            rows = data["data"]
            if not isinstance(rows, list):
                raise ValueError()
            ids = sorted(
                {
                    model_id(r.get("id"))
                    for r in rows
                    if isinstance(r, dict)
                    and model_id(r.get("id")) != "<invalid-or-redacted>"
                }
            )
            if not ids:
                raise ValueError()
            result["available_models"] = ids[:100]
            if (
                settings["model"] in ids
                and settings["model"] not in result["available_models"]
            ):
                result["available_models"].append(settings["model"])
            result["selected_model_available"] = settings["model"] in ids
            return {
                **result,
                "status": "ok" if settings["model"] in ids else "model_not_listed",
                "message": "模型列表查询成功；请核对完整 id。列表可能不含全部模型，请同时核对供应商控制台；列表可访问不代表聊天参数或生成速度已验证。",
            }
    except requests.RequestException as exc:
        return {
            **result,
            "status": llm.connection_error(exc).code,
            "message": "尚未取得可用模型列表；请根据错误类型排查网络、代理、证书或地址。",
        }
    except (ValueError, KeyError, TypeError):
        return {
            **result,
            "status": "model_list_invalid",
            "message": "接口未返回有效模型列表；未显示原始响应内容。",
        }


def main():
    result = probe()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
