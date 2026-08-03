from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    conversation_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional UUID returned by a previous response to continue that conversation.",
    )
    current_screen: str | None = Field(default=None, max_length=500)
    knowledge_source_id: UUID | None = Field(
        default=None,
        description="Optional source UUID to answer from one uploaded version only.",
    )


class Source(BaseModel):
    screen_id: str
    title: str | None = None
    module: str | None = None


class ChatResponse(BaseModel):
    answer: dict | str
    conversation_id: str
    intent: str
    token_usage: int
    sources: list[Source] = []
