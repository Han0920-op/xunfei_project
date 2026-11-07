import base64
import hashlib
import hmac
import json
import ssl
import time
from datetime import datetime
from time import mktime
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time

import websocket  # websocket-client
import requests

import config


IMAGE_UNDERSTANDING_URL = "wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image"


class VisionError(Exception):
    """图片理解调用失败时抛出。"""


class Ws_Param:
    def __init__(self, app_id, api_key, api_secret, url):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = urlparse(url).netloc
        self.path = urlparse(url).path
        self.url = url

    # 生成带鉴权签名的 WebSocket URL
    def create_url(self):
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + self.host + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + self.path + " HTTP/1.1"

        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode("utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_sha_base64}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

        v = {"authorization": authorization, "date": date, "host": self.host}
        return self.url + "?" + urlencode(v)


def gen_params(app_id, question, image_base64):
    return {
        "header": {"app_id": app_id},
        "parameter": {
            "chat": {
                "domain": "imagev3",
                "temperature": 0.5,
                "top_k": 4,
                "max_tokens": min(max(config.VISION_MAX_TOKENS, 200), 2028),
                "auditing": "default",
            }
        },
        "payload": {
            "message": {
                "text": [
                    {"role": "user", "content": image_base64, "content_type": "image"},
                    {"role": "user", "content": question},
                ]
            }
        },
    }


def understand_image(image_bytes: bytes, question: str) -> str:
    provider = config.vision_provider()
    if provider in ("deepseek", "qwen"):
        return _compatible_image(image_bytes, question)
    if provider != "xfyun":
        raise VisionError("图片模型配置不正确，请检查 VISION_PROVIDER。")
    return _xfyun_image(image_bytes, question)


def _compatible_image(image_bytes: bytes, question: str) -> str:
    qwen = config.vision_provider() == "qwen"
    base = (config.QWEN_BASE_URL if qwen else config.DEEPSEEK_VISION_BASE_URL).rstrip("/")
    key = config.DASHSCOPE_API_KEY if qwen else config.DEEPSEEK_VISION_API_KEY
    model = config.QWEN_VISION_MODEL if qwen else config.DEEPSEEK_VISION_MODEL
    if qwen and not key:
        raise VisionError("请配置百炼 DASHSCOPE_API_KEY。")
    parsed = urlparse(base)
    if not base or parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VisionError("请配置所选图片模型的推理服务地址。")
    if parsed.hostname in ("api.deepseek.com", "api.deepseek.cn") or model in ("deepseek-chat", "deepseek-reasoner"):
        raise VisionError("普通 DeepSeek 文字接口不能作为 VL2 图片推理服务，请配置独立视觉端点。")
    mime = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/webp" if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP" else "image/jpeg"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    body = {"model": model, "stream": False,
            "max_tokens": min(max(config.VISION_MAX_TOKENS, 200), 2028),
            "temperature": 0.2,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," + base64.b64encode(image_bytes).decode("ascii")}}
            ]}]}
    try:
        with requests.post(base + "/chat/completions", json=body, headers=headers,
                           timeout=(5, 40), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise VisionError("视觉服务未完成请求，请检查服务地址、模型与授权。")
            parts, size, deadline = [], 0, time.monotonic() + 45
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 1000000 or time.monotonic() > deadline:
                    raise VisionError("图片理解响应超出限制，请重试。")
                parts.append(chunk)
            data = json.loads(b"".join(parts))
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise VisionError("图片理解尚未完整结束，请重试。")
            answer = choice["message"]["content"]
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 20000:
                raise VisionError("图片理解没有返回可用观察。")
            return answer.strip()
    except VisionError:
        raise
    except Exception:
        raise VisionError("图片理解暂时无法完成，请检查视觉服务配置或稍后重试。") from None


def _xfyun_image(image_bytes: bytes, question: str) -> str:
    if not config.XFYUN_APP_ID or not config.XFYUN_API_KEY or not config.XFYUN_API_SECRET:
        raise VisionError("缺少图片理解所需配置：XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET")

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    ws_param = Ws_Param(config.XFYUN_APP_ID, config.XFYUN_API_KEY, config.XFYUN_API_SECRET, IMAGE_UNDERSTANDING_URL)
    deadline = time.monotonic() + 45
    connection = None
    answer_parts = []
    try:
        connection = websocket.create_connection(
            ws_param.create_url(), timeout=15, sslopt={"cert_reqs": ssl.CERT_REQUIRED},
        )
        connection.send(json.dumps(gen_params(config.XFYUN_APP_ID, question, image_base64)))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VisionError("图片理解超时，请稍后重试。")
            connection.settimeout(min(remaining, 15))
            raw = connection.recv()
            if not raw:
                raise VisionError("图片理解未返回完整结果，请重试。")
            data = json.loads(raw)
            if data["header"]["code"] != 0:
                error = VisionError("图片理解接口未成功完成请求，请检查配置或稍后重试。")
                if type(data["header"]["code"]) is int:
                    error.provider_code = data["header"]["code"]
                raise error
            choices = data["payload"]["choices"]
            content = choices["text"][0]["content"]
            if not isinstance(content, str):
                raise ValueError("invalid content")
            answer_parts.append(content)
            if sum(map(len, answer_parts)) > 20000:
                raise VisionError("图片理解返回内容异常，请重试。")
            if choices["status"] == 2:
                answer = "".join(answer_parts).strip()
                if not answer:
                    raise VisionError("图片理解没有返回可用观察。")
                return answer
    except VisionError:
        raise
    except Exception:
        # Signed URLs and provider errors can carry credentials; keep them private.
        raise VisionError("图片理解暂时无法完成，请检查服务配置或稍后重试。") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
