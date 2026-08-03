import json
from uuid import UUID, uuid4
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import authorize_request, get_db
from app.api.schemas.agent import ChatResponse, Source
from app.services.conversation_service import ConversationService
from app.services.navigation_agent import APMSNavigationAgent
from app.services.speech_service import SpeechService
from app.core.logger import logger

router = APIRouter(
    prefix="/agent",
    tags=["APMS Navigation Agent"],
)

speech_service = SpeechService()


@router.get("/chat/ui", include_in_schema=False)
def chat_ui():
    return FileResponse(Path(__file__).resolve().parents[2] / "static" / "chat.html")


def _conversation_id(value: str | None) -> str:

    if value:
        try:
            cid = UUID(value)
            if cid.version == 4:
                return str(cid)
        except ValueError:
            pass

        logger.warning("Ignoring invalid conversation_id supplied by client")

    return str(uuid4())


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    current_screen: str | None = Form(None),
    knowledge_source_id: UUID | None = Form(None),
    db: Session = Depends(get_db),
    _: str = Depends(authorize_request),
):

    conversation_id = _conversation_id(conversation_id)

    speech_result = await speech_service.transcribe(audio)

    message = speech_result["text"]

    conversations = ConversationService(db)

    history = conversations.history(conversation_id)

    conversations.add(
        conversation_id,
        "user",
        message,
    )

    result = APMSNavigationAgent(
        db,
        knowledge_source_id=knowledge_source_id,
    ).answer(
        message,
        history,
        current_screen=current_screen,
    )

    persisted_answer = (
        json.dumps(result.answer, ensure_ascii=False)
        if isinstance(result.answer, dict)
        else result.answer
    )

    conversations.add(
        conversation_id,
        "assistant",
        persisted_answer,
        result.token_usage,
    )

    return ChatResponse(
        answer=result.answer,
        conversation_id=conversation_id,
        intent=result.intent,
        token_usage=result.token_usage,
        sources=[Source(**source) for source in result.sources],
    )


@router.post("/chat/clear")
def clear_chat(
    conversation_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(authorize_request),
):

    try:
        valid_id = str(UUID(conversation_id))

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="conversation_id must be a UUID.",
        ) from exc

    ConversationService(db).repository.clear_messages(valid_id)

    return {
        "status": "cleared",
        "conversation_id": valid_id,
    }
