import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from vision import understand_image
import agent
import llm
from database import Base, engine, get_db, SessionLocal
from models import Case, Conversation, Message, Recheck
from pesticides import CheckRequest, check_registration
from knowledge import SearchRequest, AssistRequest, search as search_wheat, assist as assist_wheat
from chat_api import router as farmer_agent_router
from runtime import APP_VERSION, FrontendFiles
import personal
import memory


def _ensure_case_columns():
    """为已存在的 cases 表补齐后来新增的列（create_all 不会改旧表结构）。"""
    inspector = inspect(engine)
    if "cases" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("cases")}
    with engine.begin() as conn:
        if "recognition" not in existing:
            conn.execute(text("ALTER TABLE cases ADD COLUMN recognition TEXT DEFAULT ''"))
        if "advice" not in existing:
            conn.execute(text("ALTER TABLE cases ADD COLUMN advice TEXT DEFAULT ''"))
        if "conversation_id" not in existing:
            conn.execute(text("ALTER TABLE cases ADD COLUMN conversation_id INTEGER"))
        # 旧数据把「识别描述」存进了 summary，回填到 recognition（幂等），保证详情页有内容。
        conn.execute(
            text("UPDATE cases SET recognition = summary WHERE recognition = '' AND summary != ''")
        )


def _backfill_conversation_ids():
    """为旧案例（conversation_id 为空）尝试可靠地回填会话关联。

    只有当一个案例的识别描述能「唯一」定位到某条用户图片分析消息（即匹配到的
    会话恰好只有一个）时才回填，绝不随意绑定到其它会话。旧数据识别描述可能为空
    或与多条会话撞车，此时一律保持 None，交给复查时重新建立会话。
    """
    db = SessionLocal()
    try:
        orphans = db.query(Case).filter(Case.conversation_id.is_(None)).all()
        for case in orphans:
            key = (case.recognition or "").strip()
            if not key:
                continue
            cids = {
                m.conversation_id
                for m in db.query(Message)
                .filter(Message.role == "user", Message.content.contains(key))
                .all()
                if m.conversation_id is not None
            }
            if len(cids) == 1:
                case.conversation_id = cids.pop()
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时，根据 models 里定义的类自动创建表（表已存在则跳过）。
    Base.metadata.create_all(bind=engine)
    # create_all 只会建新表，不会给已存在的旧表加列，这里手动补齐后来新增的列。
    _ensure_case_columns()
    # 旧案例没有 conversation_id 的，按识别描述唯一匹配尝试回填，不匹配的保持 None。
    _backfill_conversation_ids()
    scheduler_stop = personal.start()
    try:
        yield
    finally:
        scheduler_stop.set()


app = FastAPI(title="智麦 农业智能体后端", version=APP_VERSION, lifespan=lifespan)
app.include_router(farmer_agent_router)
app.include_router(personal.router)
app.include_router(memory.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# 上传的图片统一保存到这个目录，并通过 /uploads 路径对外提供访问。
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None  # 不传就新建一个会话
    vision_result: Optional[str] = None  # 图片视觉模型的分析结果（首次上传图片时带上）
    case_id: Optional[int] = None  # 关联的历史案例（图片上传时返回），首次诊断时带上
    image_path: Optional[str] = None  # 本次图片在服务器上的路径（复查时用于记录图片）


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int  # 返回给前端，用于后续继续这个会话
    case_id: Optional[int] = None  # 回显关联的案例 ID


class CaseListItem(BaseModel):
    id: int
    thumbnail: str       # 列表卡片上的小图地址
    create_time: str     # 格式化好的时间字符串
    status: str
    summary: str
    conversation_id: Optional[int] = None  # 关联的会话 ID（旧案例可能为 None）


class CaseDetail(BaseModel):
    id: int
    image: str           # 详情页的大图地址
    create_time: str
    status: str          # 进行中 / 已完成 / 失败
    recognition: str     # 图片识别描述
    diagnosis: str       # 农业诊断结论
    advice: str          # 诊断建议
    conversation_id: Optional[int] = None  # 关联的会话 ID（旧案例可能为 None）
    last_recheck_time: Optional[str] = None
    last_recheck_diagnosis: Optional[str] = None
    recheck_count: int = 0


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: str


class RecheckItem(BaseModel):
    id: int
    rechecked_at: str
    description: str
    image: str
    recognition: str
    diagnosis: str


def _remove_upload_file(path: str):
    """删除 uploads/ 目录下的一张图片（按相对 URL 反查），失败也不影响删除流程。"""
    if not path or not path.startswith("/uploads/"):
        return
    try:
        target = os.path.join(UPLOAD_DIR, os.path.basename(path))
        if os.path.exists(target):
            os.remove(target)
    except OSError:
        pass


def _format_time(dt):
    """把 datetime 转成字符串，方便前端直接展示。"""
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def _save_image(image_bytes: bytes, content_type: str, filename: str) -> str:
    """把图片字节写入 uploads/ 目录，返回可被前端访问的相对 URL。"""
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = ext_map.get(content_type)
    if ext is None:
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(image_bytes)
    return f"/uploads/{name}"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/pesticides/check")
def pesticide_check(req: CheckRequest):
    return check_registration(req)


@app.post("/api/knowledge/search")
def knowledge_search(req: SearchRequest):
    return search_wheat(req.query)


@app.post("/api/knowledge/assist")
def knowledge_assist(req: AssistRequest):
    return assist_wheat(req.description, req.distribution, req.stage)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    # 1. 确定会话：没传 conversation_id 就新建，传了就去数据库里找。
    if req.conversation_id is None:
        conversation = Conversation()
        db.add(conversation)
        db.commit()
        db.refresh(conversation)  # 刷新后拿到数据库生成的自增 id
        conversation_id = conversation.id
    else:
        conversation = db.get(Conversation, req.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        conversation_id = conversation.id

    # 2. 从数据库按时间顺序读取这个会话的历史消息。
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )

    # 3. 组装「历史 + 当前用户消息」。若本轮带了图片视觉分析结果，就把它拼进
    #    当前用户消息，让文本模型也能“看到”图片信息。system 提示词由 agent 内部注入。
    user_content = req.message
    if req.vision_result:
        user_content = (
            "【图片视觉分析结果】\n"
            f"{req.vision_result}\n\n"
            f"【用户问题】\n{req.message}"
        )
    history_messages = [{"role": m.role, "content": m.content} for m in history]
    history_messages.append({"role": "user", "content": user_content})

    # 4. 调用 Agent 编排循环（内含工具调用决策与执行）。
    try:
        reply = agent.run(history_messages)
    except llm.LLMError as exc:
        # 本次诊断关联了案例时，把案例标记为「失败」。
        if req.case_id is not None:
            case = db.get(Case, req.case_id)
            if case is not None:
                case.status = "失败"
                db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    # 5. 把这一轮的用户消息和 AI 回复都保存到数据库。
    db.add(Message(conversation_id=conversation_id, role="user", content=user_content))
    db.add(Message(conversation_id=conversation_id, role="assistant", content=reply))

    # 6. 关联案例与会话；首次诊断写结论，复查则追加复查记录。
    if req.case_id is not None:
        case = db.get(Case, req.case_id)
        if case is not None:
            if case.conversation_id is None:
                case.conversation_id = conversation_id
            if req.vision_result:
                if not case.diagnosis:
                    # 首次诊断：结论写回案例。状态保持「进行中」（仍在跟踪），
                    # 只有用户手动「结束跟踪」才会变成「已完成」。
                    case.diagnosis = reply
                else:
                    # 复查：追加一条复查记录，不覆盖原诊断结论。
                    db.add(Recheck(
                        case_id=case.id,
                        description=req.message,
                        image_path=req.image_path or "",
                        recognition=req.vision_result,
                        diagnosis=reply,
                    ))
                    # 已结束跟踪的案例又有了新的复查数据，重新回到「进行中」。
                    if case.status == "已完成":
                        case.status = "进行中"

    db.commit()
    return ChatResponse(reply=reply, conversation_id=conversation_id, case_id=req.case_id)


def _sse(payload: dict) -> str:
    """把一段数据封装成 SSE 格式（data: <json>\n\n）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _mark_case_failed(case_id: Optional[int]):
    """流式调用失败时，把关联案例标记为「失败」。"""
    if case_id is None:
        return
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        if case is not None:
            case.status = "失败"
            db.commit()
    finally:
        db.close()


def _save_stream_reply(conversation_id: int, req: ChatRequest, reply: str):
    """流式输出结束后，落库 assistant 消息并更新案例（逻辑与 /chat 第 5、6 步一致）。"""
    db = SessionLocal()
    try:
        db.add(Message(conversation_id=conversation_id, role="assistant", content=reply))

        if req.case_id is not None:
            case = db.get(Case, req.case_id)
            if case is not None:
                if case.conversation_id is None:
                    case.conversation_id = conversation_id
                if req.vision_result:
                    if not case.diagnosis:
                        case.diagnosis = reply
                    else:
                        db.add(Recheck(
                            case_id=case.id,
                            description=req.message,
                            image_path=req.image_path or "",
                            recognition=req.vision_result,
                            diagnosis=reply,
                        ))
                        if case.status == "已完成":
                            case.status = "进行中"
        db.commit()
    finally:
        db.close()


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, db: Session = Depends(get_db)):
    # 1. 确定会话（同 /chat）。
    if req.conversation_id is None:
        conversation = Conversation()
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        conversation_id = conversation.id
    else:
        conversation = db.get(Conversation, req.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        conversation_id = conversation.id

    # 2. 读历史消息。
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )

    # 3. 组装「历史 + 当前用户消息」（同 /chat）。system 提示词由 agent 内部注入。
    user_content = req.message
    if req.vision_result:
        user_content = (
            "【图片视觉分析结果】\n"
            f"{req.vision_result}\n\n"
            f"【用户问题】\n{req.message}"
        )
    history_messages = [{"role": m.role, "content": m.content} for m in history]
    history_messages.append({"role": "user", "content": user_content})

    # 4. 先把用户消息落库，保证流中断时用户的话也不会丢。
    db.add(Message(conversation_id=conversation_id, role="user", content=user_content))
    db.commit()

    def gen():
        full = ""
        try:
            # 遍历 Agent 编排循环产出的三类事件：工具调用 / 工具结果 / 最终回答增量。
            for event in agent.run_stream(history_messages):
                etype = event["type"]
                if etype == "tool_call":
                    yield _sse({"tool_call": {"tool": event["tool"], "args": event["args"]}})
                elif etype == "tool_result":
                    yield _sse({"tool_result": {"tool": event["tool"], "result": event["result"]}})
                elif etype == "delta":
                    full += event["content"]
                    yield _sse({"delta": event["content"]})
        except llm.LLMError as exc:
            _mark_case_failed(req.case_id)
            yield _sse({"error": str(exc), "conversation_id": conversation_id, "case_id": req.case_id})
            return

        _save_stream_reply(conversation_id, req, full)
        yield _sse({"done": True, "conversation_id": conversation_id, "case_id": req.case_id})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/vision/upload")
async def upload_image(
    file: UploadFile = File(...),
    question: str = Form(...),
    case_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="暂不支持该图片格式，请上传 JPG / PNG / WEBP 图片")
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="图片内容为空")
    if len(image_bytes) > 4 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片超过 4 MB，请换一张较小的图片")
    try:
        result = understand_image(image_bytes, question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片分析失败: {str(e)}")

    image_url = _save_image(image_bytes, file.content_type, file.filename)

    # 复查模式：传了 case_id 表示给已有案例追加新图片，只识别、不新建案例。
    if case_id is not None:
        case = db.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="案例不存在")
        return {"result": result, "image_path": image_url, "case_id": case_id}

    # 新案例模式：保存图片 + 新建一条「进行中」的历史案例。
    case = Case(image_path=image_url, summary=result[:100], recognition=result, status="进行中")
    db.add(case)
    db.commit()
    db.refresh(case)
    return {"result": result, "image_path": image_url, "case_id": case.id}


@app.get("/history/list", response_model=list[CaseListItem])
def history_list(db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc(), Case.id.desc()).all()
    return [
        CaseListItem(
            id=c.id,
            thumbnail=c.image_path,
            create_time=_format_time(c.created_at),
            status=c.status,
            summary=c.summary,
            conversation_id=c.conversation_id,
        )
        for c in cases
    ]


@app.get("/history/detail/{case_id}", response_model=CaseDetail)
def history_detail(case_id: int, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")
    rechecks = (
        db.query(Recheck)
        .filter(Recheck.case_id == case_id)
        .order_by(Recheck.id.desc())
        .all()
    )
    last_recheck = rechecks[0] if rechecks else None
    return CaseDetail(
        id=case.id,
        image=case.image_path,
        create_time=_format_time(case.created_at),
        status=case.status,
        recognition=case.recognition,
        diagnosis=case.diagnosis,
        advice=case.advice,
        conversation_id=case.conversation_id,
        last_recheck_time=_format_time(last_recheck.rechecked_at) if last_recheck else None,
        last_recheck_diagnosis=last_recheck.diagnosis if last_recheck else None,
        recheck_count=len(rechecks),
    )


@app.delete("/history/{case_id}")
def history_delete(case_id: int, db: Session = Depends(get_db)):
    """删除一个案例（连同它的复查记录），不影响关联的会话和聊天消息。"""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")

    # 收集要清理的图片路径（案例图 + 各次复查图），只删本案例自己的文件。
    image_paths = [p for p in (case.image_path, *[r.image_path for r in case.rechecks]) if p]
    db.delete(case)  # ORM 级联会一并删除 rechecks；Conversation/Message 无外键，不受影响
    db.commit()

    for path in image_paths:
        _remove_upload_file(path)
    return {"ok": True}


@app.post("/history/{case_id}/finish")
def history_finish(case_id: int, db: Session = Depends(get_db)):
    """手动结束跟踪：把案例标记为「已完成」。"""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")
    case.status = "已完成"
    db.commit()
    return {"ok": True, "status": case.status}


@app.post("/history/compare")
async def history_compare(
    case_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="图片内容为空")

    question = "请详细描述这张小麦图片当前的生长状况，包括叶片颜色、斑点、异常程度等可见特征"
    try:
        new_analysis = understand_image(image_bytes, question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片分析失败: {str(e)}")

    # MVP 版先返回「历史诊断 + 新图片分析」；真正的对比结论可再用 llm.chat 生成。
    return {
        "case_id": case.id,
        "old_diagnosis": case.diagnosis or case.summary,
        "new_analysis": new_analysis,
    }


@app.get("/conversation/{conversation_id}/messages", response_model=list[MessageItem])
def conversation_messages(conversation_id: int, db: Session = Depends(get_db)):
    """按会话 ID 读回完整聊天记录，供页面刷新 / 复查恢复使用。"""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )
    return [
        MessageItem(role=m.role, content=m.content, created_at=_format_time(m.created_at))
        for m in messages
    ]


@app.get("/history/{case_id}/rechecks", response_model=list[RecheckItem])
def history_rechecks(case_id: int, db: Session = Depends(get_db)):
    """返回某个案例的全部复查记录（按时间先后）。"""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")
    rechecks = (
        db.query(Recheck)
        .filter(Recheck.case_id == case_id)
        .order_by(Recheck.id)
        .all()
    )
    return [
        RecheckItem(
            id=r.id,
            rechecked_at=_format_time(r.rechecked_at),
            description=r.description,
            image=r.image_path,
            recognition=r.recognition,
            diagnosis=r.diagnosis,
        )
        for r in rechecks
    ]


# Mount last: API routes take precedence. One origin avoids extra frontend setup.
_frontend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "front_end"))
if os.path.isdir(_frontend):
    app.mount("/", FrontendFiles(directory=_frontend, html=True), name="farmer_frontend")

