from fastapi import APIRouter
from sqlalchemy import text

from app.database.db import SessionLocal

router = APIRouter(tags=["Operations"])


@router.get("/health")
def health() -> dict[str, str]:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    return {"status": "ok"}
