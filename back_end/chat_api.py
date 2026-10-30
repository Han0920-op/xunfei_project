"""Farmer chat API: validated current image + bounded local history, SSE events."""
import io
import json
import warnings
import asyncio
import time
import logging
import uuid
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

import config
import dialogue
from runtime import APP_VERSION, STREAM_PROTOCOL
from chat_errors import error_event

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/agent")
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000, strict=True)


def prepare_image(content, content_type):
    supported = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
    if content_type not in supported:
        raise HTTPException(400, "请发送 JPG、PNG 或 WEBP 照片。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as probe:
                if probe.format != supported[content_type] or probe.width * probe.height > 24_000_000:
                    raise ValueError("format or dimensions")
                probe.verify()
            with Image.open(io.BytesIO(content)) as original:
                image = ImageOps.exif_transpose(original)
                image.thumbnail((1600, 1600))
                if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    clean = Image.new("RGB", rgba.size, "white")
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    clean = image.convert("RGB")
                output = io.BytesIO()
                # Strip EXIF/location metadata; bound payload for the vision provider.
                clean.save(output, format="JPEG", quality=85)
                return output.getvalue()
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "照片无法读取、格式不符或分辨率过大，请换一张清晰照片。") from None


@router.get("/capabilities")
def capabilities():
    # Presence only: configured does not establish successful provider connectivity.
    return JSONResponse({
        "server_version": APP_VERSION,
        "stream_protocol": STREAM_PROTOCOL,
        "chat_configured": bool(config.SPARK_API_PASSWORD),
        "vision_configured": all([config.XFYUN_APP_ID, config.XFYUN_API_KEY, config.XFYUN_API_SECRET]),
        "weather_configured": bool(config.WEATHER_API_KEY),
        "note": "配置状态不代表外部接口已通过连通性验证。",
    }, headers={"Cache-Control": "no-store"})


SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
               "X-Zhimai-Version": APP_VERSION}


@router.get("/stream-check")
async def stream_check():
    """Explicit transport probe, not model output; no keys/model calls required."""
    async def events():
        started = time.monotonic()
        for sequence in range(3):
            if sequence:
                await asyncio.sleep(0.4)
            yield "data: " + json.dumps({"type": "probe", "sequence": sequence,
                "server_elapsed_ms": round((time.monotonic() - started) * 1000),
                "server_version": APP_VERSION, "stream_protocol": STREAM_PROTOCOL}) + "\n\n"
        yield 'data: {"type":"done"}\n\n'
    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/chat")
async def chat(message: str = Form(""), history: str = Form("[]"), image: UploadFile | None = File(None),
               protocol: str | None = Header(None, alias="X-Zhimai-Stream-Protocol")):
    if protocol != STREAM_PROTOCOL:
        raise HTTPException(409, "页面版本较旧或前后端版本不一致，请拉取最新代码、重启后端，再按 Ctrl+F5 强制刷新。输入和照片仍保留。")
    if len(message) > 4000 or len(history) > 250_000:
        raise HTTPException(400, "文字或历史记录过长，请缩短后重试。")
    try:
        messages = TypeAdapter(list[HistoryMessage]).validate_json(history)
        if len(messages) > 40:
            raise ValueError("history too long")
    except (ValidationError, ValueError):
        raise HTTPException(400, "对话记录格式不正确，请刷新后重试。") from None
    image_bytes = None
    if image is not None:
        try:
            content = await image.read(MAX_IMAGE_BYTES + 1)
            if not content or len(content) > MAX_IMAGE_BYTES:
                raise HTTPException(400, "照片为空或超过10 MB，请换一张较小的照片。")
            image_bytes = prepare_image(content, image.content_type)
        finally:
            await image.close()
    if not message.strip() and not image_bytes:
        raise HTTPException(400, "请先说说情况，或选择一张照片再发送。")

    def events():
        started = time.monotonic()
        request_id = uuid.uuid4().hex[:12]
        metrics = {"model_calls": 0, "upstream_content_chunks": 0}
        delta_count = 0
        first_delta = last_delta = None
        yield "data: " + json.dumps({"type": "start", "request_id": request_id, "server_version": APP_VERSION,
                                      "stream_protocol": STREAM_PROTOCOL}) + "\n\n"
        def guarded_turn():
            try:
                with closing(dialogue.run_turn(message, [m.model_dump() for m in messages], image_bytes, metrics=metrics)) as turn:
                    yield from turn
            except Exception:
                yield error_event("internal_error")

        for event in guarded_turn():
            if event["type"] == "error":
                event = {**event, "request_id": request_id}
                event["message"] += f" 诊断编号：{request_id}。"
                logger.warning("chat_failed request_id=%s code=%s", request_id, event.get("code", "chat_not_completed"))
            if event["type"] == "answer_delta":
                delta_count += 1
                last_delta = round((time.monotonic() - started) * 1000)
                if first_delta is None:
                    first_delta = last_delta
            if event["type"] in ("done", "error"):
                stats = {"type": "stream_stats", **metrics, "answer_delta_events": delta_count,
                         "first_answer_ms": first_delta, "last_answer_ms": last_delta,
                         "total_ms": round((time.monotonic() - started) * 1000)}
                yield "data: " + json.dumps(stats) + "\n\n"
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
