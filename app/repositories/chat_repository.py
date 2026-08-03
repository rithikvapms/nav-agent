from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_messages(self, conversation_id: str) -> list[dict[str, str]]:
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
            .all()
        )
        return [{"role": message.role, "content": message.content} for message in messages]

    def add_message(
        self, conversation_id: str, role: str, content: str, token_usage: int = 0
    ) -> None:
        self.db.add(
            ChatMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                token_usage=token_usage,
            )
        )
        self.db.commit()

    def clear_messages(self, conversation_id: str) -> None:
        (
            self.db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation_id)
            .delete(synchronize_session=False)
        )
        self.db.commit()
