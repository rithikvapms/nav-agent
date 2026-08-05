"""
Identity Guard

Handles questions about the assistant's identity, capabilities,
and implementation without invoking the LLM.

This prevents hallucinations and keeps responses consistent.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class IdentityResponse:
    handled: bool
    answer: str | None = None


class IdentityGuard:

    # Regex patterns mapped to deterministic responses
    _IDENTITY_RULES = [
        (
            re.compile(
                r"\b(which|what)\s+(ai\s+)?(model|llm)\b|\bwhat\s+model\s+are\s+you\s+using\b",
                re.IGNORECASE,
            ),
            (
                "I'm the APMS AI Navigation Assistant, designed to help users "
                "navigate the APMS platform. The underlying AI implementation "
                "details are not disclosed."
            ),
        ),
        (
            re.compile(
                r"\bare\s+you\s+(chatgpt|gpt|gpt-4|claude|gemini|llama)\b",
                re.IGNORECASE,
            ),
            (
                "No. I'm the APMS AI Navigation Assistant, built specifically "
                "to assist users in navigating the APMS application."
            ),
        ),
        (
            re.compile(
                r"\bwho\s+(created|built|developed)\s+you\b",
                re.IGNORECASE,
            ),
            (
                "I was developed as part of the APMS AI Navigation system to "
                "assist users in navigating the APMS platform."
            ),
        ),
        (
            re.compile(
                r"\bwho\s+are\s+you\b",
                re.IGNORECASE,
            ),
            (
                "I'm the APMS AI Navigation Assistant. I help users navigate "
                "the APMS platform by providing accurate navigation guidance "
                "and answering platform-related questions."
            ),
        ),
        (
            re.compile(
                r"\bwhat\s+can\s+you\s+do\b",
                re.IGNORECASE,
            ),
            (
                "I can help you navigate the APMS application, explain screens, "
                "locate features, guide you through workflows, and answer "
                "questions related to the APMS platform."
            ),
        ),
        (
            re.compile(
                r"\bcan\s+you\s+access\s+the\s+internet\b",
                re.IGNORECASE,
            ),
            (
                "I'm the APMS AI Navigation Assistant. I help users navigate "
                "the APMS platform by providing accurate navigation guidance "
                "and answering platform-related questions."
            ),
        ),
    ]

    @classmethod
    def check(cls, question: str) -> IdentityResponse:
        """
        Check whether the question is about the assistant's identity.

        Returns:
            IdentityResponse(
                handled=True,
                answer="..."
            )

        or

            IdentityResponse(
                handled=False
            )
        """

        question = question.strip()

        for pattern, response in cls._IDENTITY_RULES:

            if pattern.search(question):

                return IdentityResponse(
                    handled=True,
                    answer=response,
                )

        return IdentityResponse(handled=False)
