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

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

import config
import dialogue
from runtime import APP_VERSION, STREAM_PROTOCOL
from chat_errors import error_event
from diagnostics import Trace
from response_stream import is_control_envelope

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
        "diagnostics_version": "safe-trace-v1",
        "chat_configured": config.text_configured(),
        "chat_provider": config.text_provider(),
        "chat_model": config.text_settings()["model"] if config.text_provider() in ("spark", "deepseek") else None,
        "vision_provider": config.vision_provider(),
        "vision_model": config.DEEPSEEK_VISION_MODEL if config.vision_provider() == "deepseek" else "imagev3",
        "vision_configured": config.vision_configured(),
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
async def chat(request: Request, message: str = Form(""), history: str = Form("[]"), image: UploadFile | None = File(None),
               protocol: str | None = Header(None, alias="X-Zhimai-Stream-Protocol"),
               case_id: str = Form(""), turn_id: str = Form(""), photo_id: str = Form(""), region_subscription_id: str = Form("")):
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

    import memory, personal
    try:
        actor=personal.owner(request)
    except HTTPException:
        actor=None
    if case_id:
        if not actor:raise HTTPException(401,"长期记忆身份未连接，请刷新页面后重试。输入和照片仍保留。")
        memory.identifier(case_id)
        memory.identifier(turn_id)
        if photo_id:memory.identifier(photo_id)
    confirmed=memory.fact_context(actor,case_id or None) if actor else []
    if actor and case_id:
        with memory.db() as c:
            old=c.execute('SELECT archived FROM memory_cases WHERE owner=? AND id=?',(actor,case_id)).fetchone()
            if old and old['archived']:raise HTTPException(409,'案例已结束，请先在案例页面重新打开，再继续咨询。')
    # Recover a completed request after a lost SSE connection without paying for
    # another model call or replaying write tools. IDs cannot be reused for new input.
    if actor and case_id and turn_id:
        with memory.db() as c:
            row=c.execute('SELECT body,owner,case_id FROM memory_turns WHERE id=?',(turn_id,)).fetchone()
            if row:
                if row['owner']!=actor or row['case_id']!=case_id:raise HTTPException(409,'请求编号已使用，请开始新的请求。')
                saved=json.loads(row['body'])
                if saved['user']['text']!=(message or '帮我看看这张照片') or bool(saved['user'].get('had_image'))!=bool(image_bytes):raise HTTPException(409,'重试内容已变化，请开始新的请求。')
                if image_bytes:
                    old_photo=c.execute('SELECT content FROM case_photos WHERE owner=? AND case_id=? AND id=?',(actor,case_id,saved['user'].get('photoId'))).fetchone()
                    if not old_photo or bytes(old_photo['content'])!=image_bytes:raise HTTPException(409,'重试照片已变化，请开始新的请求。')
                title=memory.owned(c,actor,case_id)['title']
                replay_id=uuid.uuid4().hex[:12]
                def replay():
                    frames=[{'type':'start','request_id':replay_id,'server_version':APP_VERSION,'stream_protocol':STREAM_PROTOCOL}, {'type':'status','message':'正在恢复这次已保存的回答…'}]
                    if saved['assistant'].get('regionalContext'):frames.append({'type':'regional_context',**saved['assistant']['regionalContext']})
                    frames.extend({'type':'vision_result',**v} for v in saved['assistant'].get('vision',[]))
                    frames.extend({'type':'tool_result',**t} for t in saved['assistant'].get('toolResults',[]))
                    frames.extend([{'type':'answer','content':saved['assistant']['text']},{'type':'memory_saved','case_id':case_id},{'type':'case_title','case_id':case_id,'title':title},{'type':'done'}])
                    for frame in frames:yield 'data: '+json.dumps(frame,ensure_ascii=False)+'\n\n'
                return StreamingResponse(replay(),media_type='text/event-stream',headers={**SSE_HEADERS,'X-Request-ID':replay_id})
    if actor and case_id and not messages:
        try:
            old_case=memory.get_case(actor,case_id)
        except HTTPException as exc:
            if exc.status_code!=404:raise
        else:
            for turn in old_case['turns'][-15:]:
                observations='；'.join(v.get('content','')[:700] for v in turn['assistant'].get('vision',[]) if v.get('status')=='ok')
                past=('【此前该轮图片的初步观察，非本轮新识别】'+observations+'\n') if observations else ''
                prior_reply=turn['assistant']['text']
                if is_control_envelope(prior_reply):prior_reply='此前回复是未执行的工具文本，不代表已创建提醒；请重新确认日期时间。'
                messages.extend([HistoryMessage(role='user',content=turn['user']['text'][:6000]),
                    HistoryMessage(role='assistant',content=past+'【此前回答】（模型历史判断，未经确认）'+prior_reply[:4000])])
    import regional_context
    if region_subscription_id:memory.identifier(region_subscription_id)
    regional=regional_context.context(actor,region_subscription_id)
    regional_prompt=regional_context.prompt_context(regional)
    request_id = uuid.uuid4().hex[:12]

    def events():
        started = time.monotonic()
        trace = Trace(request_id)
        import personal
        try:
            trace.owner = personal.owner(request)
        except HTTPException:
            trace.owner = None
        trace.case_id=case_id or None
        trace.turn_id=turn_id or request_id
        trace.memory_facts=confirmed
        trace.regional_context=regional_prompt
        import casework
        try:trace.case_state=casework.snapshot(actor,case_id)['state'] if actor and case_id else None
        except HTTPException:trace.case_state=None
        trace.log("sse.start", history_messages=len(messages), has_image=bool(image_bytes))
        metrics = {"model_calls": 0, "upstream_content_chunks": 0}
        delta_count = 0
        first_delta = last_delta = None
        yield "data: " + json.dumps({"type": "start", "request_id": request_id, "server_version": APP_VERSION,
                                      "stream_protocol": STREAM_PROTOCOL}) + "\n\n"
        def guarded_turn():
            try:
                with closing(dialogue.run_turn(message, [m.model_dump() for m in messages], image_bytes, metrics=metrics, trace=trace)) as turn:
                    yield from turn
            except Exception as exc:
                trace.log("sse.generator_failed", exc=exc)
                yield error_event("internal_error")

        saved_answer=None
        vision=[]
        tool_results=[]
        if confirmed:
            yield "data: " + json.dumps({'type':'memory_context','facts':confirmed,'case_id':case_id},ensure_ascii=False) + "\n\n"
        if actor:
            yield 'data: '+json.dumps({'type':'regional_context',**regional_prompt},ensure_ascii=False)+'\n\n'
        for event in guarded_turn():
            if event['type']=='vision_result':vision.append(event)
            if event['type']=='tool_result':tool_results.append({'tool':event['tool'],'result':event['result']})
            if event['type']=='answer':saved_answer=event['content']
            if event['type']=='done' and actor and case_id and saved_answer:
                try:
                    memory.save_turn(actor,case_id,turn_id,message,saved_answer,vision,tool_results,bool(image_bytes),photo_id,image_bytes,getattr(trace,'case_assessment',None),regional_prompt,initial_title='新诊断')
                    yield 'data: '+json.dumps({'type':'memory_saved','case_id':case_id})+'\n\n'
                    try:
                        import case_titles
                        title=case_titles.save_once(actor,case_id,getattr(trace,'generated_title',None),message,vision)
                        yield 'data: '+json.dumps({'type':'case_title','case_id':case_id,'title':title},ensure_ascii=False)+'\n\n'
                    except Exception:
                        pass  # Title failure cannot fail an already saved chat.

                except Exception as exc:
                    trace.log('memory.save_failed',exc=exc)
                    event=error_event('internal_error')

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
                trace.log("sse." + event["type"], **metrics)
                stats = {"type": "stream_stats", **metrics, "answer_delta_events": delta_count,
                         "first_answer_ms": first_delta, "last_answer_ms": last_delta,
                         "total_ms": round((time.monotonic() - started) * 1000)}
                yield "data: " + json.dumps(stats) + "\n\n"
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={**SSE_HEADERS, "X-Request-ID": request_id})
