from __future__ import annotations

import io
import logging
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


class TTSService:
    """Kokoro ONNX text-to-speech service; one loaded engine per API process."""

    def __init__(self, model_path: str | Path, voices_path: str | Path, voice: str = "af_sarah") -> None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError("kokoro-onnx is required for voice responses") from exc
        model = Path(model_path)
        voices = Path(voices_path)
        if not model.is_file() or not voices.is_file():
            raise RuntimeError(
                f"Kokoro assets not found. Expected model={model} and voices={voices}."
            )
        self._engine = Kokoro(str(model), str(voices))
        self.voice = voice
        self._lock = Lock()
        logger.info("Kokoro TTS loaded | model=%s | voice=%s", model, voice)

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise ValueError("TTS text cannot be empty")
        with self._lock:
            samples, sample_rate = self._engine.create(
                text.strip(), voice=self.voice, speed=1.0, lang="en-us"
            )
        audio = np.asarray(samples, dtype=np.float32)
        buffer = io.BytesIO()
        sf.write(buffer, audio, int(sample_rate), format="WAV", subtype="PCM_16")
        return buffer.getvalue()
