import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.db import Base


class NavigationNode(Base):
    __tablename__ = "navigation_nodes"
    __table_args__ = (UniqueConstraint("knowledge_source_id", "screen_id", name="uq_navigation_node_source_screen"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    screen_id = Column(Text, nullable=False)
    route = Column(Text)
    title = Column(Text)
    module = Column(Text)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
