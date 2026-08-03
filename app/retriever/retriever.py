from app.embeddings.embedder import Embedder
from app.repositories.screen_repository import ScreenRepository
from app.core.logger import logger


class Retriever:

    def __init__(self, repository: ScreenRepository):
        self.repository = repository
        self.embedder = Embedder()

    def retrieve(self, query: str, top_k: int = 5, knowledge_source_id=None):

        query_embedding = self.embedder.encode(query)

        results = self.repository.search_similar(
            query_embedding, top_k, knowledge_source_id
        )

        formatted_results = []

        for chunk, score in results:

            formatted_results.append({"score": float(score), "chunk": chunk})

        logger.info(
            "Retriever | Query='%s' | Matches=%d",
            query,
            len(formatted_results),
        )

        return formatted_results
