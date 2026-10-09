from contextlib import asynccontextmanager
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import config
import llm
from database import Base, engine, get_db
from models import Conversation, Message


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时，根据 models 里定义的类自动创建表（表已存在则跳过）。
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="智麦 农业智能体后端", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None  # 不传就新建一个会话


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int  # 返回给前端，用于后续继续这个会话


@app.get("/health")
def health():
    return {"status": "ok"}


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

    # 3. 组装大模型需要的 messages 格式：system + 历史 + 当前用户消息。
    messages = []
    if config.SYSTEM_PROMPT:
        messages.append({"role": "system", "content": config.SYSTEM_PROMPT})
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    # 4. 调用现有的大模型接口（完全复用 llm.chat，不改动）。
    try:
        reply = llm.chat(messages)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # 5. 把这一轮的用户消息和 AI 回复都保存到数据库。
    db.add(Message(conversation_id=conversation_id, role="user", content=req.message))
    db.add(Message(conversation_id=conversation_id, role="assistant", content=reply))
    db.commit()

    return ChatResponse(reply=reply, conversation_id=conversation_id)
