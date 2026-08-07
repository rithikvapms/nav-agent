from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
import soundfile as sf

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
            logger.info("Uploaded audio | file=%s | bytes=%d | content_type=%s", input_path.name, input_path.stat().st_size, audio.content_type)

            self._convert_to_wav(
                input_path=input_path,
                output_path=output_path,
            )

            vad_result = self.vad_service.analyze(output_path)

            if not vad_result["has_speech"]:
                return {"status": "retry", "reason": "no_speech", "message": "I couldn't hear you clearly. Please say that again."}

            if vad_result["speech_duration"] < self.MIN_SPEECH_DURATION:
                return {"status": "retry", "reason": "very_short_speech", "message": "That was too short to understand. Please say that again."}

            wav_file = open(output_path, "rb")
            wav_upload = UploadFile(
                filename="audio.wav",
                file=wav_file,
            )
            try:
                speech_result = await self.speech_service.transcribe(wav_upload)
            finally:
                wav_file.close()

            transcript = speech_result["text"].strip()

            retry = self.validation_service.validate(
                transcript, speech_result.get("duration", vad_result["speech_duration"])
            )
            self._log_wav_diagnostics(output_path)
            self._save_debug_artifacts(input_path, output_path)
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

        logger.info("FFmpeg output | format=wav | sample_rate=16000 | channels=1 | codec=pcm_s16le | bytes=%d", output_path.stat().st_size)

    @staticmethod
    def _log_wav_diagnostics(path: Path) -> None:
        info = sf.info(str(path))
        logger.info("Audio diagnostics | duration=%.3fs | sample_rate=%d | channels=%d | format=%s | subtype=%s", info.duration, info.samplerate, info.channels, info.format, info.subtype)

    @staticmethod
    def _save_debug_artifacts(input_path: Path, output_path: Path) -> None:
        if os.getenv("DEBUG", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return
        debug_dir = Path(os.getenv("AUDIO_DEBUG_DIR", "debug/audio"))
        debug_dir.mkdir(parents=True, exist_ok=True)
        request_stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        shutil.copy2(input_path, debug_dir / f"{request_stamp}-original{input_path.suffix.lower() or '.webm'}")
        shutil.copy2(output_path, debug_dir / f"{request_stamp}-converted.wav")
        logger.info("Saved audio diagnostics | directory=%s | id=%s", debug_dir, request_stamp)
