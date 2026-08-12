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
    ) -> None:

        self.repository.save(
            conversation_id=conversation_id,
            status="awaiting_clarification",
            state={
                "intent": intent,
                "target": target,
                "candidate_screen_ids": candidate_screen_ids,
            },
        )

    def clear(
        self,
        conversation_id: str,
    ) -> None:

        self.repository.clear(conversation_id)
