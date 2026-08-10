"""Filter retrieved context to end-user information before prompt construction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SanitizedChunk:
    screen_id: str = ""
    chunk_type: str = "user-facing information"
    title: str | None = None
    module: str | None = None
    content: str = ""


class RetrievalContextSanitizer:
    """Produces prompt-only chunks; it never changes retrieval results or API data."""

    _EXPLANATION = re.compile(r"\b(explain|about|say|what\s+is|what\s+are|tell\s+me)\b", re.IGNORECASE)
    _ALLOWED = {"title", "description", "business purpose", "purpose", "capabilities", "capability", "features", "feature", "overview", "summary"}
    _BLOCKED = re.compile(r"\b(screen[_ -]?id|permission|entry[_ -]?point|exit[_ -]?point|navigation|graph|workflow|developer|route|metadata)\b", re.IGNORECASE)
    _BLOCKED_PERMISSION_VALUE = re.compile(
    r"\b[a-z0-9_]+\.(view|create|update|delete|approve|export|edit)\b",
    re.IGNORECASE,)
    _BLOCKED_SCREEN_VALUE = re.compile(
    r"\b[A-Za-z ]+ Screen\s+\d+\b",
    re.IGNORECASE,)

    def is_explanation_request(self, question: str) -> bool:
        return bool(self._EXPLANATION.search(question))

    def sanitize(self, retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for result in retrieved:
            chunk = result["chunk"]
            content = self._user_content(str(chunk.content or ""))
            fingerprint = " ".join(content.lower().split())
            if not content or fingerprint in seen:
                continue
            seen.add(fingerprint)
            sanitized.append({
                "score": result["score"],
                "chunk": SanitizedChunk(title=chunk.title, module=chunk.module, content=content),
            })
        return sanitized

    def _user_content(self, content: str) -> str:
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        if parsed is not None:
            values = self._allowed_values(parsed)
            return "\n".join(values)

        lines = []

        for line in content.splitlines():
            key, separator, value = line.partition(":")

            if self._BLOCKED.search(key):
                continue

            if separator and key.strip().lower() not in self._ALLOWED:
                continue

            clean = line.strip()

            # Remove permission identifiers
            clean = self._BLOCKED_PERMISSION_VALUE.sub("", clean)

            # Remove screen names
            clean = self._BLOCKED_SCREEN_VALUE.sub("", clean)

            # Clean extra spaces and punctuation
            clean = re.sub(r"\s{2,}", " ", clean).strip(" -,:;")

            if clean and not self._BLOCKED.search(clean):
                lines.append(clean)

        return "\n".join(lines)

    def _allowed_values(self, value: Any, parent_key: str = "") -> list[str]:
        if not isinstance(value, dict):
            return []

        values = []
        seen = set()

        def add_text(text: str):
            if not text:
                return

            # Remove permission identifiers
            text = self._BLOCKED_PERMISSION_VALUE.sub("", text)

            # Remove screen names
            text = self._BLOCKED_SCREEN_VALUE.sub("", text)

            # Remove extra whitespace
            text = re.sub(r"\s{2,}", " ", text).strip(" -,:;")

            if text and text.lower() not in seen:
                seen.add(text.lower())
                values.append(text)

        for key, item in value.items():
            normalized = key.replace("_", " ").lower()

            if normalized not in self._ALLOWED:
                continue

            # Simple string
            if isinstance(item, str):
                add_text(item)

            # List values
            elif isinstance(item, list):
                for entry in item:

                    if isinstance(entry, str):
                        add_text(entry)

                    elif isinstance(entry, dict):

                        for field in (
                            "description",
                            "purpose",
                            "summary",
                            "overview",
                            "feature",
                            "features",
                            "capability",
                            "capabilities",
                        ):
                            if field in entry:
                                field_value = entry[field]

                                if isinstance(field_value, str):
                                    add_text(field_value)

                                elif isinstance(field_value, list):
                                    for v in field_value:
                                        if isinstance(v, str):
                                            add_text(v)

        return values
