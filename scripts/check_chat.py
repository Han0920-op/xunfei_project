"""Opt-in real chat probe using the application's transport and response parser.

At most two small generation requests. No images, history, tools, secrets, raw
provider text or exception messages are printed. This is not a farm diagnosis.
"""

import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler

BACKEND = Path(__file__).resolve().parents[1] / "back_end"
sys.path.insert(0, str(BACKEND))
import config
import llm
from diagnostics import exception_metadata
from response_stream import stream_response, ResponseFormatError
from runtime import APP_VERSION
from check_model import model_id

MESSAGES = [
    {
        "role": "system",
        "content": '这是接口连通性测试。请只返回 JSON：{"action":"answer","content":"连接测试成功"}。不要调用工具，不要输出其他文字。',
    },
    {"role": "user", "content": "请完成连接测试。"},
]


class ProbeTrace:
    def __init__(self):
        self.started = time.monotonic()
        self.deadline = self.started + 65
        self.http_status = None

    def log(self, stage, **fields):
        if stage == "model.http_response" and type(fields.get("status_code")) is int:
            self.http_status = fields["status_code"]


def runtime_check(settings):
    # Only this loopback readiness request skips proxies. Provider requests keep
    # the application's normal proxy and TLS settings unchanged.
    try:
        with build_opener(ProxyHandler({})).open(
            "http://127.0.0.1:8000/api/agent/capabilities", timeout=3
        ) as response:
            data = json.loads(response.read(65536))
        if not isinstance(data, dict):
            raise ValueError()
        result = {
            "server_version": model_id(data.get("server_version")),
            "chat_provider": model_id(data.get("chat_provider")),
            "chat_model": model_id(data.get("chat_model")),
        }
        matches = (
            data.get("chat_provider") == settings["provider"]
            and data.get("chat_model") == settings["model"]
        )
        result["status"] = "matches" if matches else "model_config_differs"
        result["version_matches"] = data.get("server_version") == APP_VERSION
        result["note"] = "仅对照版本、供应商和模型名称，不比较密钥及完整运行环境。"
        return result
    except (OSError, ValueError, TypeError):
        return {
            "status": "not_readable",
            "note": "未读取到本机 8000 端口的智麦状态，可先启动后端；不影响下面的直接接口测试。",
        }


def classify(exc):
    code = exc.code if isinstance(exc, llm.LLMError) else "probe_failed"
    result = {"status": code, "exceptions": exception_metadata(exc)}
    status = getattr(exc, "status_code", None)
    if type(status) is int:
        result["http_status"] = status
    return result


def run(progress=lambda message: None):
    try:
        settings = config.text_settings()
    except ValueError:
        return {"status": "provider_not_supported"}
    report = {"provider": settings["provider"], "model": model_id(settings["model"])}
    if not settings["api_key"]:
        return {**report, "status": "model_not_configured"}
    try:
        base = settings["base_url"].rstrip("/")
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
        return {**report, "status": "model_endpoint_invalid"}
    report["api_host"] = url.hostname
    report["proxy_configured"] = bool(llm.requests.utils.get_environ_proxies(base))
    report["running_backend"] = runtime_check(settings)
    progress("正在测试真实聊天流（使用当前模型和参数；本次不自动重试）…")
    trace = ProbeTrace()
    chunks = []
    stream = llm._stream_attempt(MESSAGES, trace=trace)
    stream_result = {"content_chunks": 0, "content_chars": 0}
    try:
        for chunk in stream:
            stream_result["content_chunks"] += 1
            stream_result["content_chars"] += len(chunk)
            if "first_content_ms" not in stream_result:
                stream_result["first_content_ms"] = round(
                    (time.monotonic() - trace.started) * 1000
                )
            if stream_result["content_chars"] > 131072:
                raise llm.LLMError("模型响应过长", "model_stream_invalid")
            chunks.append(chunk)
        if not chunks:
            raise llm.LLMError("未收到正文", "model_stream_invalid")
        stream_result["status"] = "ok"
    except Exception as exc:
        stream_result.update(classify(exc))
    finally:
        stream.close()
    stream_result["elapsed_ms"] = round((time.monotonic() - trace.started) * 1000)
    if trace.http_status is not None:
        stream_result["http_status"] = trace.http_status
    report["stream"] = stream_result
    if stream_result["status"] == "ok":
        # Use the real parser, but never execute tool frames or print model text.
        try:
            events = list(stream_response(iter(chunks), require_checks=False))
            final = next((e for e in events if e["type"] == "model_result"), None)
            if not final or not final.get("content") or final.get("data") is not None:
                raise ResponseFormatError("unexpected probe result")
            report["answer_format"] = "ok"
        except (ResponseFormatError, ValueError, TypeError):
            report["answer_format"] = "answer_format_invalid"
        report["status"] = (
            "ok" if report["answer_format"] == "ok" else "answer_format_invalid"
        )
        report["note"] = (
            "已测试真实生成和智麦答案解析；这不代表长对话、照片或所有工具已验证。若网页仍失败，请提供新的诊断编号。"
        )
        return report
    # Do not spend a second request on known configuration/auth/billing failures.
    if stream_result["status"] in (
        "model_auth_failed",
        "model_payment_required",
        "model_endpoint_invalid",
        "model_request_invalid",
        "model_not_configured",
        "model_proxy_failed",
        "model_tls_failed",
        "model_rate_limited",
    ):
        report["status"] = stream_result["status"]
        return report
    progress("流式请求未完成，正在用同一配置测试普通聊天请求…")
    started = time.monotonic()
    try:
        reply = llm.chat(MESSAGES)
        report["nonstream"] = {"status": "ok", "content_chars": len(reply)}
    except Exception as exc:
        report["nonstream"] = classify(exc)
    report["nonstream"]["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    report["status"] = stream_result["status"]
    report["note"] = (
        "普通请求收到正文、流式请求失败：需重点检查流式传输和超时；也可能是两次请求之间的短暂故障，不能据此认定代理有问题。"
        if report["nonstream"]["status"] == "ok"
        else "流式和普通生成请求均失败，请结合 HTTP 状态和异常类型排查；模型列表成功不能替代生成验证。"
    )
    return report


def main():
    result = run(lambda message: print(message, flush=True))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
