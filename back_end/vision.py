import base64
import hashlib
import hmac
import json
import ssl
from datetime import datetime
from time import mktime
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time

import websocket  # websocket-client

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
                "max_tokens": 2028,
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
    if not config.XFYUN_APP_ID or not config.XFYUN_API_KEY or not config.XFYUN_API_SECRET:
        raise VisionError("缺少图片理解所需配置：XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET")

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    answer_parts = []
    error_msg = []

    def on_message(ws, message):
        data = json.loads(message)
        code = data["header"]["code"]
        if code != 0:
            error_msg.append(f"code={code}: {data}")
            ws.close()
            return
        choices = data["payload"]["choices"]
        status = choices["status"]
        answer_parts.append(choices["text"][0]["content"])
        if status == 2:
            ws.close()

    def on_error(ws, error):
        error_msg.append(str(error))

    def on_open(ws):
        ws.send(json.dumps(gen_params(config.XFYUN_APP_ID, question, image_base64)))

    ws_param = Ws_Param(
        config.XFYUN_APP_ID,
        config.XFYUN_API_KEY,
        config.XFYUN_API_SECRET,
        IMAGE_UNDERSTANDING_URL,
    )
    ws = websocket.WebSocketApp(
        ws_param.create_url(),
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
    )
    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_REQUIRED})

    if error_msg:
        raise VisionError(error_msg[0])
    return "".join(answer_parts)
