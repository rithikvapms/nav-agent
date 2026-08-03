from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.database.db import Base


class ScreenChunk(Base):
    __tablename__ = "screen_chunks"

    id = Column(BigInteger, primary_key=True, index=True)

    screen_id = Column(Text, nullable=False)
    chunk_id = Column(Text, nullable=False)
    chunk_type = Column(Text, nullable=False)

    title = Column(Text)
    module = Column(Text)

    content = Column(Text, nullable=False)

    metadata_json = Column("metadata", JSONB)

    embedding = Column(Vector(384))
    knowledge_source_id = Column(
        UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=True, index=True
    )

    created_at = Column(
        DateTime(timezone=False),
        server_default=func.now()
    )
