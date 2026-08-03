from datetime import datetime

from pydantic import BaseModel


class KnowledgeSourceResponse(BaseModel):
    id: str
    version: str
    file_name: str
    description: str | None
    status: str
    total_screens: int
    total_chunks: int
    created_at: datetime
