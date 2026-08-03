from sqlalchemy import BigInteger, Column, DateTime, Index, Text
from sqlalchemy.sql import func

from app.database.db import Base


class ChatMessage(Base):
    """A persisted message belonging to one browser conversation."""

    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True, index=True)
    conversation_id = Column(Text, nullable=False)
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    token_usage = Column(BigInteger, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_chat_messages_conversation_created", "conversation_id", "created_at"),
    )
