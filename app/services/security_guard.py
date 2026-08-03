"""Small, deterministic security boundary around model input and output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from app.core.logger import logger


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    text: str
    message: str | None = None


class SecurityGuard:
    MAX_INPUT_CHARS = 4_000
    _secret_patterns = (
        re.compile(r"\b(?:sk|gsk)_[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        re.compile(r"\b(?:postgres(?:ql)?|mysql)://[^\s]+", re.IGNORECASE),
        re.compile(
            r"\b(?:password|api[_ -]?key|token|secret)\s*[:=]\s*\S+", re.IGNORECASE
        ),
    )
    _prompt_injection = re.compile(
        r"\b(ignore|disregard|override|reveal|show)\b.{0,80}\b"
        r"(previous|above|system|developer|hidden)\b.{0,80}\b"
        r"(instruction|prompt|message|rule)\b",
        re.IGNORECASE,
    )

    @classmethod
    def check_input(cls, text: str) -> GuardResult:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()
        if not cleaned:
            logger.warning("SecurityGuard: Empty Input rejected")
            return GuardResult(False, "", "Please enter a message.")
        if len(cleaned) > cls.MAX_INPUT_CHARS:
            return GuardResult(
                False, "", "Please keep messages under 4,000 characters."
            )
        if cls._prompt_injection.search(cleaned):
            logger.warning("SecurityGuard: Empty Input rejected")
            return GuardResult(
                False,
                "",
                "I can help with your question, but I can't follow requests to override or reveal protected instructions.",
            )

        for pattern in cls._secret_patterns:
            if pattern.search(cleaned):
                logger.warning("SecurityGuard: Empty Input rejected")
                return GuardResult(
                    False,
                    "",
                    "For your security, remove passwords, API keys, tokens, and database connection strings before sending a message.",
                )
        return GuardResult(True, cleaned)

    @classmethod
    def sanitize_output(cls, text: str) -> str:
        safe_text = text or "I couldn't generate a response. Please try again."
        for pattern in cls._secret_patterns:
            safe_text = pattern.sub("[REDACTED]", safe_text)
        return safe_text
