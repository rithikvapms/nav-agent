from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.services.speech_service import SpeechService
from app.services.vad_service import VADService
from app.services.speech_validation_service import SpeechValidationService

logger = logging.getLogger(__name__)


class AudioPipelineService:
    """
    Production Audio Pipeline

    Responsibilities:
        1. Save uploaded audio
        2. Convert WebM -> WAV
        3. Run Silero VAD
        4. Validate speech
        5. Call Whisper
        6. Validate transcript

    This service NEVER:
        - Calls GPT
        - Accesses the database
        - Knows conversations
    """

    MIN_SPEECH_DURATION = 0.30

    def __init__(
        self,
        speech_service: SpeechService,
        vad_service: VADService,
        validation_service: SpeechValidationService | None = None,
    ) -> None:

        self.speech_service = speech_service
        self.vad_service = vad_service
        self.validation_service = validation_service or SpeechValidationService()

    async def process(
        self,
        audio: UploadFile,
    ) -> dict:

        temp_dir = tempfile.mkdtemp(prefix="apms_voice_")

        try:

            input_path = Path(temp_dir) / Path(audio.filename or "audio.webm").name
            output_path = Path(temp_dir) / "audio.wav"

            await self._save_upload(audio, input_path)

            self._convert_to_wav(
                input_path=input_path,
                output_path=output_path,
            )

            vad_result = self.vad_service.analyze(output_path)

            if not vad_result["has_speech"]:
                return {"status": "retry", "reason": "no_speech", "message": "I couldn't hear you clearly. Please say that again."}

            if vad_result["speech_duration"] < self.MIN_SPEECH_DURATION:
                return {"status": "retry", "reason": "very_short_speech", "message": "That was too short to understand. Please say that again."}

            wav_upload = UploadFile(
                filename="audio.wav",
                file=open(output_path, "rb"),
            )

            speech_result = await self.speech_service.transcribe(wav_upload)

            transcript = speech_result["text"].strip()

            retry = self.validation_service.validate(
                transcript, speech_result.get("duration", vad_result["speech_duration"])
            )
            if retry:
                return retry

            return speech_result

        finally:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )

    async def _save_upload(
        self,
        upload: UploadFile,
        path: Path,
    ) -> None:

        with open(path, "wb") as buffer:

            while chunk := await upload.read(1024 * 1024):
                buffer.write(chunk)

        await upload.seek(0)

    def _convert_to_wav(
        self,
        input_path: Path,
        output_path: Path,
    ) -> None:

        ffmpeg_binary = os.getenv("FFMPEG_BINARY", "ffmpeg")
        resolved_ffmpeg = shutil.which(ffmpeg_binary)
        if resolved_ffmpeg is None:
            logger.error(
                "FFmpeg executable was not found | configured=%s",
                ffmpeg_binary,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Audio conversion is unavailable because FFmpeg is not installed. "
                    "Install FFmpeg and add it to PATH, or set FFMPEG_BINARY to its executable path."
                ),
            )

        command = [
            resolved_ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logger.exception("FFmpeg conversion timed out")
            raise HTTPException(
                status_code=504,
                detail="Audio conversion timed out. Please try a shorter recording.",
            ) from exc

        if result.returncode != 0:

            logger.error(result.stderr)

            raise HTTPException(
                status_code=500,
                detail="Failed to process audio.",
            )

        if not output_path.exists():

            raise HTTPException(
                status_code=500,
                detail="Converted audio file not found.",
            )
