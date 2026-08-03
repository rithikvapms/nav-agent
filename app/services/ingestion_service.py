import json
from pathlib import Path
from uuid import UUID

from app.chunking.chunking import ScreenChunker
from app.embeddings.embedder import Embedder
from app.models.screen_chunk import ScreenChunk
from app.repositories.screen_repository import ScreenRepository


class IngestionService:

    def __init__(self, repository: ScreenRepository):
        self.repository = repository
        self.chunker = ScreenChunker()
        self.embedder = Embedder()

    def ingest(self, json_path: str, knowledge_source_id: UUID | None = None) -> int:

        with open(json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        return self.ingest_data(data, knowledge_source_id)

    def ingest_data(self, data: dict, knowledge_source_id: UUID | None = None) -> int:
        screens = data.get("screens")
        if not isinstance(screens, list):
            raise ValueError("JSON must contain a 'screens' array.")

        db_chunks = []

        for screen in screens:

            chunks = self.chunker.chunk_screen(screen)

            texts = [chunk["content"] for chunk in chunks]

            embeddings = self.embedder.encode_batch(texts)

            for chunk, embedding in zip(chunks, embeddings):

                db_chunk = ScreenChunk(
                    screen_id=chunk["screen_id"],
                    chunk_id=chunk["chunk_id"],
                    chunk_type=chunk["chunk_type"],
                    title=chunk["title"],
                    module=chunk["module"],
                    content=chunk["content"],
                    metadata_json=chunk["metadata"],
                    embedding=embedding,
                    knowledge_source_id=knowledge_source_id,
                )

                db_chunks.append(db_chunk)

        self.repository.save_all(db_chunks)

        return len(db_chunks)
