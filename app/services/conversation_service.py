from app.repositories.chat_repository import ChatRepository


class ConversationService:
    """Owns persisted conversational context for API callers."""

    def __init__(self, db):
        self.repository = ChatRepository(db)

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        return self.repository.list_messages(conversation_id)

    def add(
        self, conversation_id: str, role: str, content: str, token_usage: int = 0
    ) -> None:
        self.repository.add_message(conversation_id, role, content, token_usage)
