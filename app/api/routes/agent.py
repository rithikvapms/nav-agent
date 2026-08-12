import base64
import json
from threading import Event, Lock
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
_active_requests: dict[str, Event] = {}
_active_requests_lock = Lock()


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
    request_id: str | None = None,
    cancel_event: Event | None = None,
    generate_audio: bool = True,
) -> UnifiedVoiceResponse:
    if not generate_audio:
        return UnifiedVoiceResponse(
            status=status,
            intent=intent,
            speech=speech,
            navigation=navigation,
            audio=None,
            conversation_id=conversation_id,
            token_usage=token_usage,
            sources=[Source(**source) for source in (sources or [])],
            request_id=request_id,
        )
    if tts_service is None:
        raise HTTPException(status_code=503, detail="Voice synthesis is not ready.")
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise HTTPException(status_code=499, detail="Request was cancelled.")
        wav_bytes = await run_in_threadpool(tts_service.synthesize, speech)
        if cancel_event is not None and cancel_event.is_set():
            raise HTTPException(status_code=499, detail="Request was cancelled.")
        audio = base64.b64encode(wav_bytes).decode("ascii")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Kokoro synthesis failed")
        raise HTTPException(
            status_code=503, detail="Voice synthesis is temporarily unavailable."
        ) from exc
    return UnifiedVoiceResponse(
        status=status,
        intent=intent,
        speech=speech,
        navigation=navigation,
        audio=audio,
        conversation_id=conversation_id,
        token_usage=token_usage,
        sources=[Source(**source) for source in (sources or [])],
        request_id=request_id,
    )


def _request_event(request_id: str) -> Event:
    event = Event()
    with _active_requests_lock:
        _active_requests[request_id] = event
    return event


def _ensure_active(request_id: str, event: Event) -> None:
    if event.is_set():
        raise HTTPException(
            status_code=499, detail=f"Request {request_id} was cancelled."
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
    audio: UploadFile | None = File(None),
    message: str | None = Form(None),
    request_id: str | None = Form(None),
    conversation_id: str | None = Form(None),
    current_screen: str | None = Form(None),
    knowledge_source_id: UUID | None = Form(None),
    db: Session = Depends(get_db),
    _: str = Depends(authorize_request),
):
    request_id = request_id or str(uuid4())
    cancel_event = _request_event(request_id)
    try:
        conversation_id = _conversation_id(conversation_id)
        voice_input = audio is not None
        if audio is not None:
            speech_result = await audio_pipeline.process(audio)
            _ensure_active(request_id, cancel_event)
            if speech_result.get("status") == "retry":
                return await _voice_response(
                    "retry",
                    "repeat",
                    "Sorry, I couldn't understand you. Could you please repeat?",
                    request_id=request_id,
                    cancel_event=cancel_event,
                    generate_audio=True,
                )
            message = speech_result["text"]
        elif not message or not message.strip():
            raise HTTPException(
                status_code=422, detail="Provide either audio or message."
            )
        else:
            message = message.strip()
        _ensure_active(request_id, cancel_event)

        conversations = ConversationService(db)

        history = conversations.history(conversation_id)

        conversations.add(conversation_id, "user", message)
        _ensure_active(request_id, cancel_event)

        result = await run_in_threadpool(
            APMSNavigationAgent(
                db,
                knowledge_source_id=knowledge_source_id,
            ).answer,
            message,
            history,
            current_screen,
            conversation_id,
        )
        _ensure_active(request_id, cancel_event)

        persisted_answer = (
            json.dumps(result.answer, ensure_ascii=False)
            if isinstance(result.answer, dict)
            else result.answer
        )
        conversations.add(
            conversation_id, "assistant", persisted_answer, result.token_usage
        )

        if result.intent == "navigate":
            navigation = (
                result.answer
                if isinstance(result.answer, dict)
                else {
                    "status": "not_found",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": str(result.answer),
                    "steps": [],
                    "sources": [],
                }
            )

            navigation_status = navigation.get(
                "status",
                "not_found",
            )

            # ---------------------------------------------------------
            # Successful navigation
            # ---------------------------------------------------------
            if navigation_status == "success":
                screen = navigation.get("screen") or {}

                screen_name = (
                    screen.get("title")
                    or screen.get("id")
                    or "the requested screen"
                )

                speech = (
                    navigation.get("summary")
                    or f"Opening {screen_name}."
                )

                return await _voice_response(
                    "success",
                    "navigation",
                    speech,
                    navigation,
                    conversation_id,
                    result.token_usage,
                    result.sources,
                    request_id,
                    cancel_event,
                    voice_input,
                )

            # ---------------------------------------------------------
            # Multiple matching screens
            # ---------------------------------------------------------
            if navigation_status == "needs_clarification":
                speech = (
                    navigation.get("summary")
                    or "I need more information to determine which screen you mean."
                )

            if navigation_status == "navigation_unavailable":
                speech = (
                    navigation.get("summary")
                    or "The destination exists, but it is not reachable from the current screen."
                )
                return await _voice_response(
                    "navigation_unavailable",
                    "navigation",
                    speech,
                    navigation,
                    conversation_id,
                    result.token_usage,
                    result.sources,
                    request_id,
                    cancel_event,
                    voice_input,
                )

                return await _voice_response(
                    "needs_clarification",
                    "navigation",
                    speech,
                    navigation,
                    conversation_id,
                    result.token_usage,
                    result.sources,
                    request_id,
                    cancel_event,
                    voice_input,
                )

            # ---------------------------------------------------------
            # Screen not found / navigation unavailable
            # ---------------------------------------------------------
            speech = (
                navigation.get("summary")
                or "I couldn't find the requested screen."
            )

            return await _voice_response(
                "not_found",
                "navigation",
                speech,
                navigation,
                conversation_id,
                result.token_usage,
                result.sources,
                request_id,
                cancel_event,
                voice_input,
            )
        speech = (
            result.answer
            if isinstance(result.answer, str)
            else json.dumps(result.answer, ensure_ascii=False)
        )
        return await _voice_response(
            "success",
            "information",
            speech,
            conversation_id=conversation_id,
            token_usage=result.token_usage,
            sources=result.sources,
            request_id=request_id,
            cancel_event=cancel_event,
            generate_audio=voice_input,
        )
    finally:
        with _active_requests_lock:
            _active_requests.pop(request_id, None)


@router.post("/cancel/{request_id}")
def cancel_request(
    request_id: str, _: str = Depends(authorize_request)
) -> dict[str, str]:
    with _active_requests_lock:
        event = _active_requests.get(request_id)
    if event is None:
        return {"status": "not_found", "request_id": request_id}
    event.set()
    return {"status": "cancelled", "request_id": request_id}


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
