import uuid

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.db import Base


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(String(20), nullable=False)
    file_name = Column(String(255), nullable=False)
    description = Column(Text)
    uploaded_by = Column(UUID(as_uuid=True))
    status = Column(String(20), nullable=False, server_default="PROCESSING")
    total_screens = Column(Integer, nullable=False, server_default="0")
    total_chunks = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    schema_version = Column(Integer, nullable=False, server_default="1")
