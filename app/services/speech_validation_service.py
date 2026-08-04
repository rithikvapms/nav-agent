from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class SpeechValidationService:
    """Pure validation boundary between transcription and the navigation agent."""

    MIN_TRANSCRIPT_LENGTH = 2
    MIN_MEANINGFUL_WORDS = 1
    _HALLUCINATIONS = {
        "thank you for watching", "thanks for watching", "you", "the end",
        "subscribe", "please subscribe", "music", "♪",
    }

    def validate(self, transcript: str | None, speech_duration: float | None = None) -> dict[str, Any] | None:
        text = " ".join((transcript or "").split()).strip()
        if not text:
            return self._retry("empty_transcript", "I couldn't hear any words. Please say that again.")
        if len(text) < self.MIN_TRANSCRIPT_LENGTH:
            return self._retry("very_short_speech", "That was too short to understand. Please say that again.")
        normalized = re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
        if normalized in self._HALLUCINATIONS:
            return self._retry("whisper_hallucination", "I couldn't understand the speech clearly. Please try again.")
        words = normalized.split()
        if not words or not any(any(character.isalpha() for character in word) for word in words):
            return self._retry("noisy_audio", "The audio was unclear. Please speak clearly and try again.")
        if len(words) >= 4 and len(set(words)) == 1:
            return self._retry("noisy_audio", "The audio was unclear. Please speak clearly and try again.")
        if speech_duration is not None and speech_duration < 0.30:
            return self._retry("very_short_speech", "That was too short to understand. Please say that again.")
        if not any(char.isalpha() for char in text):
            return self._retry("invalid_command", "Please say a meaningful APMS request.")
        return None

    @staticmethod
    def _retry(reason: str, message: str) -> dict[str, str]:
        logger.info("Speech validation retry | reason=%s", reason)
        return {"status": "retry", "reason": reason, "message": message}
