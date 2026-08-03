from app.database.db import SessionLocal
from app.repositories.screen_repository import ScreenRepository
from app.services.ingestion_service import IngestionService


def main():

    db = SessionLocal()

    try:

        repository = ScreenRepository(db)

        service = IngestionService(repository)

        service.ingest("data/apms_ai_app.json")

    finally:

        db.close()


if __name__ == "__main__":
    main()