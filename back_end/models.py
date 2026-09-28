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
