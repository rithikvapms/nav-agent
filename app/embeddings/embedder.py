from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer


class Embedder:

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):

        self.model = self._load_model(model_name)

    @staticmethod
    @lru_cache(maxsize=2)
    def _load_model(model_name: str) -> SentenceTransformer:
        """Load each embedding model once per API worker."""
        return SentenceTransformer(model_name)

    def encode(self, text: str) -> List[float]:

        embedding = self.model.encode(
            text, convert_to_numpy=True, normalize_embeddings=True
        )

        return embedding.tolist()

    def encode_batch(self, texts: List[str]) -> List[List[float]]:

        embeddings = self.model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True
        )

        return embeddings.tolist()
