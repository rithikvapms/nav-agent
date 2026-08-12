from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from app.repositories.screen_repository import ScreenRepository


@dataclass(frozen=True)
class NavigationCandidate:
    screen_id: str
    route: str | None
    title: str | None
    module: str | None
    score: float


@dataclass(frozen=True)
class NavigationResolution:
    status: str
    candidate: NavigationCandidate | None
    candidates: list[NavigationCandidate]


class NavigationResolver:

    def __init__(self, repository: ScreenRepository):
        self.repository = repository

    def resolve(
        self,
        query: str,
        knowledge_source_id: UUID,
    ) -> NavigationResolution:

        cleaned = self._normalize(query)

        if not cleaned:
            return NavigationResolution(
                status="not_found",
                candidate=None,
                candidates=[],
            )

        # ---------------------------------------------------------
        # 1. Exact screen_id
        # ---------------------------------------------------------

        candidates = self.repository.find_navigation_node(
            knowledge_source_id,
            screen_id=cleaned,
        )

        if len(candidates) == 1:
            return self._resolved(candidates[0], 1.0)

        # ---------------------------------------------------------
        # 2. Exact route
        # ---------------------------------------------------------

        candidates = self.repository.find_navigation_node(
            knowledge_source_id,
            route=cleaned,
        )

        if len(candidates) == 1:
            return self._resolved(candidates[0], 1.0)

        # ---------------------------------------------------------
        # 3. Exact title
        # ---------------------------------------------------------

        candidates = self.repository.find_navigation_node(
            knowledge_source_id,
            title=cleaned,
        )

        if len(candidates) == 1:
            return self._resolved(candidates[0], 0.98)

        # ---------------------------------------------------------
        # 4. Exact module
        # ---------------------------------------------------------

        candidates = self.repository.find_navigation_node(
            knowledge_source_id,
            module=cleaned,
        )

        if len(candidates) == 1:
            return self._resolved(candidates[0], 0.95)

        if len(candidates) > 1:
            scored = self._score_candidates(
                cleaned,
                candidates,
            )

            return NavigationResolution(
                status="ambiguous",
                candidate=None,
                candidates=scored[:5],
            )

        # ---------------------------------------------------------
        # 5. Normalized partial search
        # ---------------------------------------------------------

        candidates = self.repository.search_navigation_nodes(
            knowledge_source_id,
            cleaned,
            limit=10,
        )

        scored = self._score_candidates(
            cleaned,
            candidates,
        )

        if not scored:
            return NavigationResolution(
                status="not_found",
                candidate=None,
                candidates=[],
            )

        # ---------------------------------------------------------
        # 6. Confidence decision
        # ---------------------------------------------------------

        best = scored[0]

        if best.score >= 0.90:
            return NavigationResolution(
                status="resolved",
                candidate=best,
                candidates=scored,
            )

        if best.score >= 0.65:
            return NavigationResolution(
                status="ambiguous",
                candidate=None,
                candidates=scored[:5],
            )

        return NavigationResolution(
            status="not_found",
            candidate=None,
            candidates=scored,
        )

    def _score_candidates(
        self,
        query: str,
        nodes,
    ) -> list[NavigationCandidate]:

        query_tokens = set(self._tokens(query))

        results = []

        for node in nodes:

            score = 0.0

            screen_id = self._normalize(node.screen_id)

            title = self._normalize(node.title or "")

            module = self._normalize(node.module or "")

            route = self._normalize(node.route or "")

            # Exact normalized match
            if query == title:
                score = max(score, 0.98)

            if query == module:
                score = max(score, 0.95)

            if query == screen_id:
                score = max(score, 1.0)

            # Token overlap
            candidate_tokens = set(self._tokens(f"{title} {module} {screen_id}"))

            if query_tokens and candidate_tokens:

                overlap = len(query_tokens & candidate_tokens) / len(query_tokens)

                score = max(
                    score,
                    overlap * 0.85,
                )

            # Substring match
            if query in title:
                score = max(score, 0.88)

            elif query in module:
                score = max(score, 0.82)

            elif query in screen_id:
                score = max(score, 0.78)

            elif query in route:
                score = max(score, 0.75)

            if score > 0:
                results.append(
                    NavigationCandidate(
                        screen_id=node.screen_id,
                        route=node.route,
                        title=node.title,
                        module=node.module,
                        score=round(score, 4),
                    )
                )

        return sorted(
            results,
            key=lambda item: item.score,
            reverse=True,
        )

    @staticmethod
    def _resolved(
        node,
        score: float,
    ) -> NavigationResolution:

        candidate = NavigationCandidate(
            screen_id=node.screen_id,
            route=node.route,
            title=node.title,
            module=node.module,
            score=score,
        )

        return NavigationResolution(
            status="resolved",
            candidate=candidate,
            candidates=[candidate],
        )

    @staticmethod
    def _normalize(value: str) -> str:

        value = value.strip().lower()

        value = value.replace("_", " ")
        value = value.replace("-", " ")

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    @staticmethod
    def _tokens(value: str) -> list[str]:

        return re.findall(
            r"[a-z0-9]+",
            value.lower(),
        )
