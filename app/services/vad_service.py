from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import soundfile as sf

logger = logging.getLogger(__name__)


class VADService:
    """Silero VAD using SoundFile, NumPy, and ONNX Runtime only."""

    SAMPLE_RATE = 16_000
    CHUNK_SIZE = 512
    CONTEXT_SIZE = 64
    THRESHOLD = 0.5
    MIN_SPEECH_SAMPLES = int(0.25 * SAMPLE_RATE)
    MIN_SILENCE_SAMPLES = int(0.10 * SAMPLE_RATE)

    def __init__(self, model_path: str | Path | None = None) -> None:
        resolved_model = self._resolve_model_path(model_path)
        logger.info("Loading Silero ONNX VAD | model=%s", resolved_model)
        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(str(resolved_model), providers=["CPUExecutionProvider"], sess_options=options)
        self._input_names = {item.name for item in self.session.get_inputs()}
        logger.info("Silero ONNX VAD loaded successfully")

    @staticmethod
    def _resolve_model_path(model_path: str | Path | None) -> Path:
        project_model = Path(__file__).resolve().parents[2] / "models" / "silero_vad.onnx"
        candidates = [
            Path(model_path) if model_path else None,
            Path(os.getenv("SILERO_VAD_MODEL", "")) if os.getenv("SILERO_VAD_MODEL") else None,
            project_model,
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate
        raise RuntimeError(
            "Silero ONNX model was not found. Restore models/silero_vad.onnx "
            "or set SILERO_VAD_MODEL to a valid model path."
        )

    def analyze(self, wav_path: str | Path) -> dict[str, Any]:
        try:
            audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
            audio = np.asarray(audio, dtype=np.float32)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            if audio.ndim != 1 or audio.size == 0:
                raise ValueError("Audio is empty or has an unsupported channel layout")
            if sample_rate != self.SAMPLE_RATE:
                raise ValueError(f"Expected {self.SAMPLE_RATE} Hz WAV, received {sample_rate} Hz")
            probabilities = self._probabilities(np.clip(audio, -1.0, 1.0))
            segments = self._segments(probabilities, len(audio))
            speech_duration = sum(item["end"] - item["start"] for item in segments) / self.SAMPLE_RATE
            result = {"has_speech": bool(segments), "speech_duration": round(speech_duration, 2), "segments": segments}
            logger.info("VAD | speech=%s | duration=%.2fs | segments=%d", result["has_speech"], speech_duration, len(segments))
            return result
        except Exception:
            logger.exception("VAD analysis failed | file=%s", wav_path)
            raise

    def _probabilities(self, audio: np.ndarray) -> list[float]:
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, self.CONTEXT_SIZE), dtype=np.float32)
        probabilities: list[float] = []
        padded = np.pad(audio, (0, (-len(audio)) % self.CHUNK_SIZE))
        for offset in range(0, len(padded), self.CHUNK_SIZE):
            model_input = np.concatenate((context, padded[offset : offset + self.CHUNK_SIZE][None, :]), axis=1)
            inputs = {"input": model_input, "state": state, "sr": np.array(self.SAMPLE_RATE, dtype=np.int64)}
            outputs = self.session.run(None, {key: value for key, value in inputs.items() if key in self._input_names})
            probabilities.append(float(np.asarray(outputs[0]).reshape(-1)[0]))
            if len(outputs) > 1:
                state = np.asarray(outputs[1], dtype=np.float32)
            context = model_input[:, -self.CONTEXT_SIZE :]
        return probabilities

    def _segments(self, probabilities: list[float], audio_length: int) -> list[dict[str, int]]:
        segments: list[dict[str, int]] = []
        start: int | None = None
        silence = 0
        for index, probability in enumerate(probabilities):
            sample_start = index * self.CHUNK_SIZE
            if probability >= self.THRESHOLD and start is None:
                start, silence = sample_start, 0
            elif start is not None and probability < self.THRESHOLD:
                silence += self.CHUNK_SIZE
                if silence >= self.MIN_SILENCE_SAMPLES:
                    end = min(sample_start + self.CHUNK_SIZE, audio_length)
                    if end - start >= self.MIN_SPEECH_SAMPLES:
                        segments.append({"start": start, "end": end})
                    start, silence = None, 0
        if start is not None and audio_length - start >= self.MIN_SPEECH_SAMPLES:
            segments.append({"start": start, "end": audio_length})
        return segments
