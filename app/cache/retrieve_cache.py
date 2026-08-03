from cachetools import TTLCache
from app.embeddings.embedder import Embedder
from app.repositories.screen_repository import ScreenRepository

# Cache up to 1000 different queries for 10 minutes
retrieval_cache = TTLCache(maxsize=1000, ttl=600)


class Retriever:
    def __init__(self, repository: ScreenRepository):
        self.repository = repository
        self.embedder = Embedder()

    def retrieve(self, query: str, top_k: int = 5, knowledge_source_id=None):
        query = query.strip()

        if not query:
            return []

        cache_key = f"{query.lower()}:{top_k}:{knowledge_source_id or 'all'}"

        # Return cached result if available
        if cache_key in retrieval_cache:
            return retrieval_cache[cache_key]

        query_embedding = self.embedder.encode(query)

        results = self.repository.search_similar(
            query_embedding,
            top_k, knowledge_source_id
        )

        formatted_results = [
            {
                "score": float(score),
                "chunk": chunk
            }
            for chunk, score in results
        ]

        # Store in cache
        retrieval_cache[cache_key] = formatted_results

        return formatted_results
