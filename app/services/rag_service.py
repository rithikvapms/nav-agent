"""Backward-compatible import for older callers.

Use :class:`APMSNavigationAgent` for new code.
"""

from app.services.navigation_agent import APMSNavigationAgent


class RAGService(APMSNavigationAgent):
    """Compatibility façade; retained to avoid breaking existing imports."""

    def ask(self, question: str, history: list | None = None) -> str:
        return self.respond(question, history)
