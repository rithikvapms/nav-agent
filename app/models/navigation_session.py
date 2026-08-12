from sqlalchemy import Column, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database.db import Base


class NavigationSession(Base):
    """
    Stores transient navigation state for a conversation.

    This is application state, not chat history.
    """

    __tablename__ = "navigation_sessions"

    conversation_id = Column(
        Text,
        primary_key=True,
        nullable=False,
    )

    status = Column(
        Text,
        nullable=False,
        default="idle",
    )

    state = Column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_navigation_sessions_status",
            "status",
        ),
    )
