import numpy as np

from app.embeddings.embedder import Embedder

class IntentClassifier:

    def __init__(self):

        self.embedder = Embedder()

        self.chat_examples = [
            "hi",
            "hello",
            "hey",
            "how are you",
            "who are you",
            "what can you do",
            "tell me a joke",
            "what is python",
            "good morning",
            "good evening"
        ]

        self.rag_examples = [
            "create authentication",
            "update authentication",
            "delete authentication",
            "export authentication",
            "open authentication",
            "show authentication",
            "authentication permission",
            "authentication workflow",
            "authentication screen",
            "go to authentication"
        ]

        self.chat_embeddings = [
            self.embedder.encode(text)
            for text in self.chat_examples
        ]
        self.rag_embeddings = [
            self.embedder.encode(text)
            for text in self.rag_examples
        ]
    def cosine_similarity(self, a, b):

        a = np.array(a)
        b = np.array(b)

        return np.dot(a, b) / (
            np.linalg.norm(a) * np.linalg.norm(b)
        )

    def classify(self, question: str) -> str:

        query_embedding = self.embedder.encode(question)

        chat_score = max(
            self.cosine_similarity(
                query_embedding,
                embedding
            )
            for embedding in self.chat_embeddings
        )

        rag_score = max(
            self.cosine_similarity(
                query_embedding,
                embedding
            )
            for embedding in self.rag_embeddings
        )

        print(f"Chat Score : {chat_score:.4f}")
        print(f"RAG Score  : {rag_score:.4f}")

        if chat_score > rag_score:
            return "chat"

        return "rag"
