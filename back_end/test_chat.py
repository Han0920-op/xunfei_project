"""后端 /chat 接口的消息组装逻辑测试（单元/接口测试，不依赖真实大模型与视觉接口）。

通过直接调用 main.chat() 端点函数 + 内存 SQLite + 假 llm.chat，捕获最终发送给文本
大模型的 messages，验证：纯文本聊天、图片识别结果合并、连续追问历史上下文。

运行方式（在 back_end 目录下）：
    venv/Scripts/python.exe test_chat.py
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import llm
import main
from database import Base
from main import ChatRequest


def build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def run():
    Session = build_session_factory()
    captured = {}

    def fake_chat(messages):
        captured["messages"] = messages
        return "这是模拟的AI回复"

    llm.chat = fake_chat  # 替换真实大模型调用，捕获其入参

    # 场景 A：不上传图片，纯文本聊天
    db = Session()
    resp = main.chat(ChatRequest(message="你好"), db)
    db.close()
    assert resp.reply == "这是模拟的AI回复"
    assert resp.conversation_id is not None
    last_user = [m for m in captured["messages"] if m["role"] == "user"][-1]
    assert last_user["content"] == "你好", f"纯文本消息被污染: {last_user['content']!r}"
    print("[PASS] A 纯文本聊天正常，消息未被污染")

    # 场景 C：带 vision_result 的图片问题，描述必须真正进入大模型消息
    desc = "叶片整体发黄，叶尖出现红褐色锈斑，部分叶片有坏死斑点。"
    db = Session()
    resp = main.chat(
        ChatRequest(message="请分析图片中小麦的生长状态", vision_result=desc),
        db,
    )
    db.close()
    last_user = [m for m in captured["messages"] if m["role"] == "user"][-1]
    assert "【图片视觉分析结果】" in last_user["content"], last_user["content"]
    assert desc in last_user["content"], "图片描述未进入大模型消息"
    assert "【用户问题】" in last_user["content"], "用户问题缺失"
    assert "请分析图片中小麦的生长状态" in last_user["content"]
    print("[PASS] C vision_result 正确拼入最终发送给大模型的消息")

    # 场景 D：连续追问，历史中仍保留图片描述，后续问题无需重复携带 vision_result
    db = Session()
    first = main.chat(ChatRequest(message="请分析图片", vision_result=desc), db)
    cid = first.conversation_id
    second = main.chat(ChatRequest(message="那具体是什么病害？", conversation_id=cid), db)
    db.close()
    assert second.conversation_id == cid
    history_text = "\n".join(m["content"] for m in captured["messages"])
    assert desc in history_text, "追问时历史中丢失了图片描述"
    print("[PASS] D 连续追问能利用图片上下文")

    # 场景 G：多轮纯文本聊天，vision_result 为空不报错，历史正常保留
    db = Session()
    first = main.chat(ChatRequest(message="第一句"), db)
    cid2 = first.conversation_id
    second = main.chat(ChatRequest(message="第二句", conversation_id=cid2), db)
    db.close()
    assert second.conversation_id == cid2
    assert second.reply == "这是模拟的AI回复"
    print("[PASS] G 多轮纯文本聊天正常，vision_result 为空不报错")

    print("\n全部后端消息组装测试通过")


if __name__ == "__main__":
    run()
