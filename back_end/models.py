from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Conversation(Base):
    """一个独立的会话。"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), default="新对话")
    created_at = Column(DateTime, default=datetime.now)

    # 一个会话对应多条消息；删除会话时，连同它的消息一起删除。
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """会话中的一条消息。"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    # 外键：指向 conversations.id，表示这条消息属于哪个会话。
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String(20))  # user / assistant
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    conversation = relationship("Conversation", back_populates="messages")


class Case(Base):
    """一个历史诊断案例（对应「历史案例」页的一张卡片）。

    注意：它和 Conversation 是两回事——
    Conversation 存的是「聊天消息」，Case 存的是「一次诊断的记录 + 图片」。
    """
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    # 图片在服务器上的相对路径，例如 "/uploads/xxxx.jpg"，前端直接拿来当 <img src>
    image_path = Column(String(255), default="")
    # 列表页显示的一句话摘要（取识别描述前 100 字）
    summary = Column(String(500), default="")
    # 图片识别描述：视觉模型对图片的原始描述（与「诊断结论」是两个概念）
    recognition = Column(Text, default="")
    # 案例状态：进行中 / 已完成 / 失败
    status = Column(String(20), default="进行中")
    # 农业诊断结论：文本大模型给出的诊断
    diagnosis = Column(Text, default="")
    # 诊断建议：管理建议（MVP 暂未单独生成，先与结论合并存于 diagnosis）
    advice = Column(Text, default="")
    # 关联的会话 ID；旧案例没有关联会话时为 None
    conversation_id = Column(Integer, nullable=True, default=None)
    created_at = Column(DateTime, default=datetime.now)

    # 一个案例可以有多次复查
    rechecks = relationship("Recheck", back_populates="case", cascade="all, delete-orphan")


class Recheck(Base):
    """一次复查记录：同一份小麦档案在不同时间的再次检查。

    与 Message 区分：Message 存聊天流水，Recheck 存「这一次复查」的摘要快照。
    """
    __tablename__ = "rechecks"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), index=True)
    # 用户补充描述
    description = Column(Text, default="")
    # 本次复查图片（可选）
    image_path = Column(String(255), default="")
    # 本次图片识别结果（可选）
    recognition = Column(Text, default="")
    # 本次复查诊断结果
    diagnosis = Column(Text, default="")
    rechecked_at = Column(DateTime, default=datetime.now)

    case = relationship("Case", back_populates="rechecks")
