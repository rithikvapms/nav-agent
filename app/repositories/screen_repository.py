from typing import List
from uuid import UUID

from sqlalchemy.orm import Session
from app.models.screen_chunk import ScreenChunk
from sqlalchemy import select


class ScreenRepository:

    def __init__(self, db: Session):
        self.db = db

    def save(self, chunk: ScreenChunk) -> ScreenChunk:
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)

        return chunk

    def save_all(self, chunks: List[ScreenChunk]) -> None:
        self.db.add_all(chunks)
        self.db.commit()

    def get_all(self) -> List[ScreenChunk]:
        return self.db.query(ScreenChunk).all()

    def delete_all(self) -> None:
        self.db.query(ScreenChunk).delete()
        self.db.commit()

    def count(self) -> int:
        return self.db.query(ScreenChunk).count()

    def get_vocabulary_chunks(self, knowledge_source_id: UUID | None = None) -> List[ScreenChunk]:
        """Minimal fields needed to build the domain-aware typo vocabulary."""
        query = self.db.query(ScreenChunk.title, ScreenChunk.module, ScreenChunk.content)
        if knowledge_source_id:
            query = query.filter(ScreenChunk.knowledge_source_id == knowledge_source_id)
        return query.all()

    def search_similar(self, query_embedding, top_k: int = 5, knowledge_source_id: UUID | None = None):

        similarity = (
            1 - ScreenChunk.embedding.cosine_distance(query_embedding)
        ).label("score")

        query = (
            self.db.query(ScreenChunk, similarity)
            .order_by(
                ScreenChunk.embedding.cosine_distance(query_embedding)
            )
        )
        if knowledge_source_id:
            query = query.filter(ScreenChunk.knowledge_source_id == knowledge_source_id)
        results = query.limit(top_k).all()

        return results
