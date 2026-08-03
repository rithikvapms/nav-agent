"""Query cleanup and intent detection for the navigation assistant.

The correction vocabulary is built from the application's own screens.  This is
important because product names, abbreviations, and module names should not be
"corrected" by a general-purpose spell checker.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher, get_close_matches
from typing import Iterable


WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


class QueryUnderstanding:
    _navigation_vocabulary = {
        "open", "go", "to", "navigate", "show", "find", "create", "update",
        "delete", "view", "search", "export", "import", "screen", "module",
        "dashboard", "settings", "report", "reports", "permission", "permissions",
    }
    _chat_patterns = (
        r"^(hi|hello|hey|good (morning|afternoon|evening))\b",
        r"^(who are you|what can you do|tell me a joke)\b",
    )
    _navigate_pattern = re.compile(
        r"\b(open|go to|navigate|take me|show me|where is|find)\b",
        re.IGNORECASE,
    )

    def __init__(self, vocabulary: Iterable[str] = ()):
        self.vocabulary = self._navigation_vocabulary | {
            word.lower() for word in vocabulary if len(word) >= 3
        }
        self.domain_terms = self.vocabulary - self._navigation_vocabulary

    @classmethod
    def from_chunks(cls, chunks) -> "QueryUnderstanding":
        words = set()
        domain_words = set()
        for chunk in chunks:
            for value in (chunk.title, chunk.module, chunk.content):
                if value:
                    words.update(match.group(0) for match in WORD_RE.finditer(value))
            for value in (chunk.title, chunk.module):
                if value:
                    domain_words.update(match.group(0) for match in WORD_RE.finditer(value))
        instance = cls(words)
        instance.domain_terms = {word.lower() for word in domain_words if len(word) >= 3}
        return instance

    def normalize(self, question: str) -> tuple[str, list[tuple[str, str]]]:
        """Return a conservatively corrected query and the changes made."""
        changes: list[tuple[str, str]] = []

        def replace(match: re.Match) -> str:
            word = match.group(0)
            lowered = word.lower()
            if len(word) < 4 or lowered in self.vocabulary or word.isupper():
                return word

            # Short action words such as "opne" need a slightly lower threshold
            # to accommodate a transposed pair of letters.
            cutoff = 0.75 if len(word) <= 4 else 0.82
            candidates = get_close_matches(lowered, self.vocabulary, n=1, cutoff=cutoff)
            if not candidates:
                return word
            candidate = candidates[0]
            # Avoid changing a legitimate term merely because a similar term exists.
            if SequenceMatcher(None, lowered, candidate).ratio() < cutoff:
                return word
            corrected = candidate.capitalize() if word[0].isupper() else candidate
            changes.append((word, corrected))
            return corrected

        cleaned = re.sub(r"\s+", " ", question).strip()
        return WORD_RE.sub(replace, cleaned), changes

    def detect_intent(self, question: str) -> str:
        normalized = question.strip().lower()
        # Navigation wins over a greeting or other conversational text in a
        # mixed request: "Hi, how are you? Take me to Authentication."
        if self._navigate_pattern.search(normalized):
            return "navigate"
        if any(re.search(pattern, normalized) for pattern in self._chat_patterns):
            return "chat"
        # Only use the APMS knowledge base when the user is actually asking
        # about its terminology. Everything else is normal conversation.
        words = {match.group(0).lower() for match in WORD_RE.finditer(normalized)}
        return "knowledge" if words & self.domain_terms or "apms" in words else "chat"

    def retrieval_query(self, question: str, intent: str) -> str:
        """Remove conversational filler before embedding a navigation request."""
        if intent != "navigate":
            return question
        match = self._navigate_pattern.search(question)
        return question[match.start():].strip() if match else question
