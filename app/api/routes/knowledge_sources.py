import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import authorize_request, get_db
from app.api.schemas.knowledge_source import KnowledgeSourceResponse
from app.models.knowledge_source import KnowledgeSource
from app.repositories.screen_repository import ScreenRepository
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/knowledge-sources", tags=["Knowledge Sources"])


def _response(source: KnowledgeSource) -> KnowledgeSourceResponse:
    return KnowledgeSourceResponse(
        id=str(source.id), version=source.version, file_name=source.file_name,
        description=source.description, status=source.status,
        total_screens=source.total_screens, total_chunks=source.total_chunks,
        created_at=source.created_at,
    )


@router.get("/ui", include_in_schema=False)
def upload_ui() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parents[2] / "static" / "knowledge-upload.html")


@router.get("", response_model=list[KnowledgeSourceResponse])
def list_sources(db: Session = Depends(get_db), _: str = Depends(authorize_request)):
    return [_response(source) for source in db.query(KnowledgeSource).order_by(KnowledgeSource.created_at.desc()).all()]


@router.post("/upload", response_model=KnowledgeSourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_source(
    file: UploadFile = File(...), version: str = Form(...), description: str | None = Form(None),
    uploaded_by: str | None = Form(None), db: Session = Depends(get_db), _: str = Depends(authorize_request),
) -> KnowledgeSourceResponse:
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Upload a .json file.")
    try:
        data = json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="The uploaded file is not valid UTF-8 JSON.") from exc
    screens = data.get("screens") if isinstance(data, dict) else None
    if not isinstance(screens, list) or not screens:
        raise HTTPException(status_code=400, detail="JSON must contain a non-empty 'screens' array.")
    try:
        uploader_id = UUID(uploaded_by) if uploaded_by else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="uploaded_by must be a UUID.") from exc

    source = KnowledgeSource(version=version, file_name=Path(file.filename).name,
                            description=description, uploaded_by=uploader_id, status="PROCESSING")
    db.add(source)
    db.flush()
    try:
        chunk_count = IngestionService(ScreenRepository(db)).ingest_data(data, source.id)
        source.total_screens = len(screens)
        source.total_chunks = chunk_count
        source.status = "READY"
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        raise
    return _response(source)
