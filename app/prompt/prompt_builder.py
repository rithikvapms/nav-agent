"""Deprecated compatibility module. Use :mod:`app.prompts.rag` instead."""

from app.prompts.rag import build_rag_user_prompt


class PromptBuilder:
    @staticmethod
    def build(question: str, retrieved_chunks: list, intent: str, history: list | None = None) -> str:
        return build_rag_user_prompt(question, retrieved_chunks, intent, history)
