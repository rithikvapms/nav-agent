from typing import List
from uuid import UUID

from sqlalchemy import or_
from app.models.navigation_node import NavigationNode
from app.models.knowledge_source import KnowledgeSource
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
        self.db.flush()

    def get_all(self) -> List[ScreenChunk]:
        return self.db.query(ScreenChunk).all()

    def delete_all(self) -> None:
        self.db.query(ScreenChunk).delete()
        self.db.commit()

    def count(self) -> int:
        return self.db.query(ScreenChunk).count()

    def find_navigation_node(
        self,
        knowledge_source_id: UUID,
        *,
        screen_id: str | None = None,
        route: str | None = None,
        title: str | None = None,
        module: str | None = None,
    ) -> List[NavigationNode]:

        query = self.db.query(NavigationNode).filter(
            NavigationNode.knowledge_source_id == knowledge_source_id
        )

        conditions = []

        if screen_id:
            conditions.append(NavigationNode.screen_id.ilike(screen_id))

        if route:
            conditions.append(NavigationNode.route.ilike(route))

        if title:
            conditions.append(NavigationNode.title.ilike(title))

        if module:
            conditions.append(NavigationNode.module.ilike(module))

        if not conditions:
            return []

        return query.filter(or_(*conditions)).limit(20).all()

    def search_navigation_nodes(
        self,
        knowledge_source_id: UUID,
        query_text: str,
        limit: int = 10,
    ) -> List[NavigationNode]:

        normalized = query_text.strip().lower()

        if not normalized:
            return []

        search_pattern = f"%{normalized}%"

        return (
            self.db.query(NavigationNode)
            .filter(
                NavigationNode.knowledge_source_id == knowledge_source_id,
                or_(
                    NavigationNode.screen_id.ilike(search_pattern),
                    NavigationNode.title.ilike(search_pattern),
                    NavigationNode.module.ilike(search_pattern),
                    NavigationNode.route.ilike(search_pattern),
                ),
            )
            .limit(limit)
            .all()
        )

    def get_vocabulary_chunks(
        self, knowledge_source_id: UUID | None = None
    ) -> List[ScreenChunk]:
        """Minimal fields needed to build the domain-aware typo vocabulary."""
        query = self.db.query(
            ScreenChunk.title, ScreenChunk.module, ScreenChunk.content
        )
        if knowledge_source_id:
            query = query.filter(ScreenChunk.knowledge_source_id == knowledge_source_id)
        return query.all()

    def get_latest_ready_source_id(self) -> UUID | None:
        """Return the current ready graph when a caller did not pin a version."""
        source = (
            self.db.query(KnowledgeSource.id)
            .filter(KnowledgeSource.status == "READY")
            .order_by(KnowledgeSource.created_at.desc())
            .first()
        )
        return source[0] if source else None

    def search_similar(
        self, query_embedding, top_k: int = 5, knowledge_source_id: UUID | None = None
    ):

        similarity = (1 - ScreenChunk.embedding.cosine_distance(query_embedding)).label(
            "score"
        )

        query = self.db.query(ScreenChunk, similarity).order_by(
            ScreenChunk.embedding.cosine_distance(query_embedding)
        )
        if knowledge_source_id:
            query = query.filter(ScreenChunk.knowledge_source_id == knowledge_source_id)
        results = query.limit(top_k).all()

        return results
