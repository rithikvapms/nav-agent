from app.database.db import SessionLocal
from app.services.navigation_session_service import NavigationSessionService


CONVERSATION_ID = "test-navigation-conversation"


def main():
    db = SessionLocal()

    try:
        service = NavigationSessionService(db)

        # Start clean
        service.clear(CONVERSATION_ID)
        db.commit()

        # 1. Store pending clarification
        service.set_pending(
            conversation_id=CONVERSATION_ID,
            intent="navigate",
            target="dashboard",
            candidate_screen_ids=[
                "dashboard_002",
                "dashboard_014",
                "dashboard_026",
                "dashboard_050",
            ],
        )

        db.commit()

        # 2. Read it back
        session = service.get(CONVERSATION_ID)

        print("\n=== AFTER SET_PENDING ===")
        print(session)

        assert session["status"] == "awaiting_clarification"

        assert session["state"]["intent"] == "navigate"

        assert session["state"]["target"] == "dashboard"

        assert session["state"]["candidate_screen_ids"] == [
            "dashboard_002",
            "dashboard_014",
            "dashboard_026",
            "dashboard_050",
        ]

        # 3. Clear pending navigation
        service.clear(CONVERSATION_ID)

        db.commit()

        # 4. Verify clear
        session = service.get(CONVERSATION_ID)

        print("\n=== AFTER CLEAR ===")
        print(session)

        assert session["status"] == "idle"
        assert session["state"] == {}

        print("\nNavigation session test PASSED.")

    finally:
        db.close()


if __name__ == "__main__":
    main()