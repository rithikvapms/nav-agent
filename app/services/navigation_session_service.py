from app.repositories.navigation_session_repository import (
    NavigationSessionRepository,
)


class NavigationSessionService:

    def __init__(self, db):
        self.repository = NavigationSessionRepository(db)

    def get(
        self,
        conversation_id: str,
    ) -> dict:

        session = self.repository.get(conversation_id)

        if session is None:
            return {
                "status": "idle",
                "state": {},
            }

        return {
            "status": session.status,
            "state": session.state or {},
        }

    def set_pending(
        self,
        conversation_id: str,
        intent: str,
        target: str,
        candidate_screen_ids: list[str],
        knowledge_source_id: str | None = None,
    ) -> None:

        self.repository.save(
            conversation_id=conversation_id,
            status="awaiting_clarification",
            state={
                "intent": intent,
                "target": target,
                "candidate_screen_ids": candidate_screen_ids,
                "knowledge_source_id": knowledge_source_id,
            },
        )

    def clear(
        self,
        conversation_id: str,
    ) -> None:

        self.repository.clear(conversation_id)
