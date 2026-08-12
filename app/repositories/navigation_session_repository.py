from sqlalchemy.orm import Session

from app.models.navigation_session import NavigationSession


class NavigationSessionRepository:

    def __init__(self, db: Session):
        self.db = db

    def get(
        self,
        conversation_id: str,
    ) -> NavigationSession | None:

        return (
            self.db.query(NavigationSession)
            .filter(NavigationSession.conversation_id == conversation_id)
            .first()
        )

    def save(
        self,
        conversation_id: str,
        status: str,
        state: dict,
    ) -> NavigationSession:

        session = self.get(conversation_id)

        if session is None:
            session = NavigationSession(
                conversation_id=conversation_id,
                status=status,
                state=state,
            )
            self.db.add(session)
        else:
            session.status = status
            session.state = state

        self.db.flush()

        return session

    def clear(
        self,
        conversation_id: str,
    ) -> None:

        session = self.get(conversation_id)

        if session is not None:
            session.status = "idle"
            session.state = {}

            self.db.flush()
