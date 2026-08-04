import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.db import Base


class NavigationEdge(Base):
    __tablename__ = "navigation_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    from_node_id = Column(UUID(as_uuid=True), ForeignKey("navigation_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    to_node_id = Column(UUID(as_uuid=True), ForeignKey("navigation_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship = Column(String(50), nullable=False, default="navigation")
    weight = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
