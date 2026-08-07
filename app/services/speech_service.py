import logging
import os
import tempfile
import time
from pathlib import Path

from faster_whisper import WhisperModel
from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)


class SpeechService:
    """
    Production-ready Speech-to-Text Service
    """

    SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}

    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

    def __init__(self):

        self.model = WhisperModel(
            model_size_or_path=os.getenv("WHISPER_MODEL", "base"),
            device=os.getenv("WHISPER_DEVICE", "cpu"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        )

    async def transcribe(self, file: UploadFile) -> dict:

        self._validate_extension(file.filename)

        contents = await file.read()

        self._validate_file_size(len(contents))

        suffix = Path(file.filename).suffix.lower()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:

            temp_file.write(contents)
            temp_path = temp_file.name

        start = time.perf_counter()

        try:

            segments, info = self.model.transcribe(
                # The audio pipeline already runs Silero VAD on this exact WAV.
                # A second VAD pass can remove short, valid one-word commands.
                temp_path, language="en", beam_size=5, vad_filter=False
            )

            segment_list = list(segments)
            transcript = "".join(segment.text for segment in segment_list).strip()
            avg_logprob = (sum(float(getattr(segment, "avg_logprob", 0.0)) for segment in segment_list) / len(segment_list)) if segment_list else None
            no_speech = max((float(getattr(segment, "no_speech_prob", 0.0)) for segment in segment_list), default=0.0)

            processing_time = round(time.perf_counter() - start, 3)

            logger.info(
                "Speech Transcribed | file=%s | language=%s | duration=%.2fs | processing=%.2fs",
                file.filename,
                info.language,
                info.duration,
                processing_time,
            )
            logger.info("Whisper diagnostics | model=%s | language_probability=%.3f | segments=%d | avg_logprob=%s | max_no_speech_prob=%.3f | transcript=%r", os.getenv("WHISPER_MODEL", "base"), float(getattr(info, "language_probability", 0.0)), len(segment_list), avg_logprob, no_speech, transcript)
            if avg_logprob is not None and avg_logprob < -1.0:
                logger.warning("Low Whisper confidence | avg_logprob=%.3f | transcript=%r", avg_logprob, transcript)

            return {
                "text": transcript,
                "language": info.language,
                "duration": round(info.duration, 2),
                "processing_time": processing_time,
                "avg_logprob": avg_logprob,
                "no_speech_probability": no_speech,
            }

        except Exception as e:

            logger.exception("Speech transcription failed")

            raise HTTPException(
                status_code=500, detail=f"Speech transcription failed: {str(e)}"
            )

        finally:

            if os.path.exists(temp_path):
                os.remove(temp_path)

    @classmethod
    def _validate_extension(cls, filename: str):

        extension = Path(filename).suffix.lower()

        if extension not in cls.SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400, detail=f"Unsupported audio format: {extension}"
            )

    @classmethod
    def _validate_file_size(cls, size: int):

        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if size > cls.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400, detail="Audio file exceeds maximum size of 25 MB."
            )
