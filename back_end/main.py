from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import config
import llm

app = FastAPI(title="智麦 农业智能体后端", version="0.1.0")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    messages = []
    if config.SYSTEM_PROMPT:
        messages.append({"role": "system", "content": config.SYSTEM_PROMPT})
    messages.append({"role": "user", "content": req.message})

    try:
        reply = llm.chat(messages)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return ChatResponse(reply=reply)
