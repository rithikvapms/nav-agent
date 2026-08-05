import base64
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
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.dependencies import authorize_request, get_db
from app.api.schemas.agent import Source, SpeechRetryResponse, UnifiedVoiceResponse
from app.services.conversation_service import ConversationService
from app.services.navigation_agent import APMSNavigationAgent
from app.services.speech_service import SpeechService
from app.services.audio_pipeline_service import AudioPipelineService
from app.services.vad_service import VADService 
from app.core.logger import logger
from app.services.tts_service import TTSService

router = APIRouter(
    prefix="/agent",
    tags=["APMS Navigation Agent"],
)

speech_service = SpeechService()
vad_service = VADService()

audio_pipeline = AudioPipelineService(
    speech_service=speech_service,
    vad_service=vad_service,
)
tts_service: TTSService | None = None


def set_tts_service(service: TTSService) -> None:
    global tts_service
    tts_service = service


async def _voice_response(
    status: str,
    intent: str,
    speech: str,
    navigation: dict | None = None,
    conversation_id: str | None = None,
    token_usage: int = 0,
    sources: list[dict] | None = None,
) -> UnifiedVoiceResponse:
    if tts_service is None:
        raise HTTPException(status_code=503, detail="Voice synthesis is not ready.")
    try:
        wav_bytes = await run_in_threadpool(tts_service.synthesize, speech)
        audio = base64.b64encode(wav_bytes).decode("ascii")
    except Exception as exc:
        logger.exception("Kokoro synthesis failed")
        raise HTTPException(status_code=503, detail="Voice synthesis is temporarily unavailable.") from exc
    return UnifiedVoiceResponse(
        status=status, intent=intent, speech=speech, navigation=navigation, audio=audio,
        conversation_id=conversation_id, token_usage=token_usage,
        sources=[Source(**source) for source in (sources or [])],
    )


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
    response_model=UnifiedVoiceResponse,
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

    speech_result = await audio_pipeline.process(audio)

    if speech_result.get("status") == "retry":
        return await _voice_response(
            "retry", "repeat", "Sorry, I couldn't understand you. Could you please repeat?"
        )

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

    if result.intent == "navigate":
        navigation = result.answer if isinstance(result.answer, dict) else {
            "status": "success",
            "intent": "navigate",
            "screen": {"id": None, "title": None, "module": None},
            "navigation_path": [],
            "summary": str(result.answer),
            "steps": [],
            "sources": [source["screen_id"] for source in result.sources],
        }
        screen = navigation.get("screen") or {}
        screen_name = screen.get("title") or screen.get("id") or "the requested screen"
        return await _voice_response(
            "success", "navigation", f"Opening {screen_name}.", navigation,
            conversation_id, result.token_usage, result.sources,
        )
    speech = result.answer if isinstance(result.answer, str) else json.dumps(result.answer, ensure_ascii=False)
    return await _voice_response(
        "success", "information", speech, conversation_id=conversation_id,
        token_usage=result.token_usage, sources=result.sources,
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
