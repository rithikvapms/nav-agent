"""Application service that orchestrates the AI APMS Navigation Agent."""

import json
from dataclasses import dataclass

from app.prompts.rag import build_rag_user_prompt
from app.repositories.screen_repository import ScreenRepository
from app.retriever.retriever import Retriever
from app.services.llm_service import LLMService
from app.services.query_understanding import QueryUnderstanding
from app.services.navigation_graph_service import NavigationGraphService
from app.services.security_guard import SecurityGuard
from app.services.identity_guard import IdentityGuard
from app.services.retrieval_context_sanitizer import RetrievalContextSanitizer
from app.services.navigation_session_service import NavigationSessionService
from app.services.navigation_resolver import (
    NavigationResolver,
    NavigationCandidate,
)
from app.core.logger import logger


@dataclass(frozen=True)
class AgentAnswer:
    answer: dict | str
    intent: str
    sources: list[dict[str, str | None]]
    token_usage: int = 0


class APMSNavigationAgent:
    """Routes safe requests to general chat or grounded APMS retrieval."""

    def __init__(self, db, knowledge_source_id=None):
        repository = ScreenRepository(db)

        # Clients may pin a source version for reproducibility.  Otherwise
        # navigation uses the newest graph that completed ingestion; no UUID,
        # demo version, or screen is hard-coded in the engine.
        self.knowledge_source_id = (
            knowledge_source_id or repository.get_latest_ready_source_id()
        )

        self.retriever = Retriever(repository)

        self.llm = LLMService()

        self.navigation_resolver = NavigationResolver(repository)

        self.understanding = QueryUnderstanding.from_chunks(
            repository.get_vocabulary_chunks(self.knowledge_source_id)
        )

        self.graph = NavigationGraphService(db)
        self.navigation_sessions = NavigationSessionService(db)
        self.context_sanitizer = RetrievalContextSanitizer()

    def answer(
        self,
        question: str,
        history: list | None = None,
        current_screen: str | None = None,
        conversation_id: str | None = None,
    ) -> AgentAnswer:

        input_result = SecurityGuard.check_input(question)

        if not input_result.allowed:
            return AgentAnswer(
                input_result.message or "I can't process that message.",
                "blocked",
                [],
            )

        identity_result = IdentityGuard.check(input_result.text)

        if identity_result.handled:
            return AgentAnswer(
                answer=identity_result.answer,
                intent="identity",
                sources=[],
            )

        # ---------------------------------------------------------
        # 1. Check whether this conversation is waiting for a
        #    navigation clarification.
        # ---------------------------------------------------------

        if conversation_id:
            pending = self.navigation_sessions.get(conversation_id)

            if pending["status"] == "awaiting_clarification":
                return self._resolve_pending_navigation(
                    question=input_result.text,
                    conversation_id=conversation_id,
                    pending_state=pending["state"],
                    current_screen=current_screen,
                )

        # ---------------------------------------------------------
        # 2. Normalize and detect intent.
        # ---------------------------------------------------------

        normalized_question, corrections = self.understanding.normalize(
            input_result.text
        )

        intent = self.understanding.detect_intent(normalized_question)

        logger.info(
            "Intent=%s | Normalized Query=%s | Corrections=%s",
            intent,
            normalized_question,
            corrections,
        )

        # ---------------------------------------------------------
        # 3. Normal chat path.
        #
        #    Navigation does NOT enter this path.
        # ---------------------------------------------------------

        if intent == "chat":
            answer, token_usage = self.llm.generate(
                normalized_question,
                history,
                current_screen=current_screen,
            )

            return AgentAnswer(
                SecurityGuard.sanitize_output(answer),
                intent,
                [],
                token_usage,
            )

        # ---------------------------------------------------------
        # 4. Deterministic navigation path.
        # ---------------------------------------------------------

        if intent == "navigate":
            return self._handle_navigation(
                question=normalized_question,
                conversation_id=conversation_id,
                current_screen=current_screen,
            )

        # ---------------------------------------------------------
        # 5. Existing RAG / information path.
        # ---------------------------------------------------------

        retrieval_query = self.understanding.retrieval_query(
            normalized_question,
            intent,
        )

        retrieved_chunks = self.retriever.retrieve(
            retrieval_query,
            knowledge_source_id=self.knowledge_source_id,
        )

        logger.info(
            "Retrieved %d chunks",
            len(retrieved_chunks),
        )

        prompt_chunks = retrieved_chunks

        if intent != "navigate" and self.context_sanitizer.is_explanation_request(
            normalized_question
        ):
            prompt_chunks = self.context_sanitizer.sanitize(retrieved_chunks)

            logger.info(
                "Sanitized explanation context | retained=%d",
                len(prompt_chunks),
            )

        prompt = build_rag_user_prompt(
            normalized_question,
            prompt_chunks,
            intent,
            history,
            [],
        )

        sources: list[dict[str, str | None]] = []
        seen: set[str] = set()

        for item in retrieved_chunks:
            chunk = item["chunk"]

            if chunk.screen_id not in seen:
                seen.add(chunk.screen_id)

                sources.append(
                    {
                        "screen_id": chunk.screen_id,
                        "title": chunk.title,
                        "module": chunk.module,
                    }
                )

        answer, token_usage = self.llm.generate(
            prompt,
            current_screen=current_screen,
        )

        safe_answer = SecurityGuard.sanitize_output(answer)

        return AgentAnswer(
            safe_answer,
            intent,
            sources,
            token_usage,
        )

    def _handle_navigation(
        self,
        question: str,
        conversation_id: str | None,
        current_screen: str | None,
    ) -> AgentAnswer:

        if self.knowledge_source_id is None:
            return AgentAnswer(
                answer={
                    "status": "not_found",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": ("Navigation knowledge is not configured."),
                    "steps": [],
                    "sources": [],
                },
                intent="navigate",
                sources=[],
            )

        retrieval_query = self.understanding.retrieval_query(
            question,
            "navigate",
        )

        logger.info(
            "Navigation target=%s",
            retrieval_query,
        )

        resolution = self.navigation_resolver.resolve(
            query=retrieval_query,
            knowledge_source_id=self.knowledge_source_id,
        )

        if resolution.status == "resolved":
            return self._build_navigation_answer(
                resolution.candidate,
                current_screen=current_screen,
            )

        if resolution.status == "ambiguous":
            if conversation_id is None:
                return self._build_ambiguous_answer(resolution.candidates)

            candidate_ids = [candidate.screen_id for candidate in resolution.candidates]

            self.navigation_sessions.set_pending(
                conversation_id=conversation_id,
                intent="navigate",
                target=retrieval_query,
                candidate_screen_ids=candidate_ids,
                knowledge_source_id=str(self.knowledge_source_id),
            )

            return self._build_ambiguous_answer(resolution.candidates)

        return AgentAnswer(
            answer={
                "status": "not_found",
                "intent": "navigate",
                "screen": None,
                "navigation_path": [],
                "summary": (
                    f"I couldn't find a screen matching " f"'{retrieval_query}'."
                ),
                "steps": [],
                "sources": [],
            },
            intent="navigate",
            sources=[],
        )

    def _build_navigation_answer(
        self,
        candidate,
        current_screen: str | None = None,
    ) -> AgentAnswer:

        if candidate is None:
            return AgentAnswer(
                answer={
                    "status": "not_found",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": "I couldn't resolve the requested screen.",
                    "steps": [],
                    "sources": [],
                },
                intent="navigate",
                sources=[],
            )

        destination = candidate.screen_id

        graph_path = self.graph.find_path(
            self.knowledge_source_id,
            current_screen,
            destination,
        )

        if not graph_path:
            return AgentAnswer(
                answer={
                    "status": "navigation_unavailable",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": "The destination exists, but no valid navigation path is available from the current screen.",
                    "steps": [],
                    "sources": [candidate.screen_id],
                },
                intent="navigate",
                sources=[],
            )

        screen = {
            "id": candidate.screen_id,
            "title": candidate.title,
            "module": candidate.module,
            "route": candidate.route,
        }

        navigation = {
            "status": "success",
            "intent": "navigate",
            "confidence": candidate.score,
            "screen": screen,
            "navigation_path": graph_path,
            "summary": (f"Opening {candidate.title or candidate.screen_id}."),
            "steps": graph_path,
            "sources": [candidate.screen_id],
        }

        return AgentAnswer(
            answer=navigation,
            intent="navigate",
            sources=[
                {
                    "screen_id": candidate.screen_id,
                    "title": candidate.title,
                    "module": candidate.module,
                }
            ],
        )

    def _build_ambiguous_answer(
        self,
        candidates,
    ) -> AgentAnswer:

        candidate_data = [
            {
                "id": candidate.screen_id,
                "title": candidate.title,
                "module": candidate.module,
                "route": candidate.route,
            }
            for candidate in candidates
        ]

        return AgentAnswer(
            answer={
                "status": "needs_clarification",
                "intent": "navigate",
                "screen": None,
                "navigation_path": [],
                "summary": (
                    "I found multiple matching screens. "
                    "Please specify which one you mean."
                ),
                "candidates": candidate_data,
                "steps": [],
                "sources": [candidate.screen_id for candidate in candidates],
            },
            intent="navigate",
            sources=[
                {
                    "screen_id": candidate.screen_id,
                    "title": candidate.title,
                    "module": candidate.module,
                }
                for candidate in candidates
            ],
        )

    def _generate_clarification(
        self,
        target: str,
        candidates,
    ) -> AgentAnswer:

        # Kept as a compatibility shim for callers outside this service. A
        # clarification is deterministic application data, never an LLM task.
        return self._build_ambiguous_answer(candidates)

    def _resolve_pending_navigation(
        self,
        question: str,
        conversation_id: str,
        pending_state: dict,
        current_screen: str | None = None,
    ) -> AgentAnswer:

        candidate_screen_ids = pending_state.get(
            "candidate_screen_ids",
            [],
        )

        pending_source = pending_state.get("knowledge_source_id")
        if pending_source and pending_source != str(self.knowledge_source_id):
            self.navigation_sessions.clear(conversation_id)
            return AgentAnswer(
                answer={"status": "not_found", "intent": "navigate", "screen": None,
                        "navigation_path": [], "summary": "The pending navigation request belongs to a different knowledge source.",
                        "steps": [], "sources": []},
                intent="navigate", sources=[]
            )

        if not candidate_screen_ids:
            self.navigation_sessions.clear(conversation_id)

            return AgentAnswer(
                answer={
                    "status": "not_found",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": (
                        "The pending navigation request " "is no longer available."
                    ),
                    "steps": [],
                    "sources": [],
                },
                intent="navigate",
                sources=[],
            )

        normalized = question.strip().lower()

        candidates = []

        for screen_id in candidate_screen_ids:
            candidate = self.graph.get_node(
                self.knowledge_source_id,
                screen_id,
            )

            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            self.navigation_sessions.clear(conversation_id)

            return AgentAnswer(
                answer={
                    "status": "not_found",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": (
                        "The previously available navigation "
                        "targets are no longer available."
                    ),
                    "steps": [],
                    "sources": [],
                },
                intent="navigate",
                sources=[],
            )

        # ---------------------------------------------------------
        # Numeric selection:
        #
        # "2" can mean the second candidate.
        # "50" can match dashboard_050.
        # ---------------------------------------------------------

        matches = []

        for candidate in candidates:

            candidate_id = str(candidate["id"]).lower()

            title = str(candidate["title"] or "").lower()

            module = str(candidate["module"] or "").lower()

            route = str(candidate["route"] or "").lower()

            if normalized in {
                candidate_id,
                title,
                module,
                route,
            }:
                matches.append(candidate)
                continue

            if normalized in candidate_id:
                matches.append(candidate)
                continue

            if title and normalized in title:
                matches.append(candidate)
                continue

            if route and normalized in route:
                matches.append(candidate)

        # ---------------------------------------------------------
        # Ordinal selection: "first", "second", etc.
        # ---------------------------------------------------------

        ordinal_map = {
            "first": 0,
            "1st": 0,
            "second": 1,
            "2nd": 1,
            "third": 2,
            "3rd": 2,
            "fourth": 3,
            "4th": 3,
            "fifth": 4,
            "5th": 4,
        }

        if normalized in ordinal_map:
            index = ordinal_map[normalized]

            if index < len(candidates):
                matches = [candidates[index]]

        # ---------------------------------------------------------
        # Exactly one match
        # ---------------------------------------------------------

        if len(matches) == 1:

            selected = matches[0]

            self.navigation_sessions.clear(conversation_id)

            navigation_candidate = NavigationCandidate(
                screen_id=selected["id"],
                route=selected["route"],
                title=selected["title"],
                module=selected["module"],
                score=1.0,
            )

            return self._build_navigation_answer(
                navigation_candidate,
                current_screen=current_screen,
            )

        # ---------------------------------------------------------
        # Multiple matches
        # ---------------------------------------------------------

        if len(matches) > 1:

            candidate_data = [
                {
                    "id": candidate["id"],
                    "title": candidate["title"],
                    "module": candidate["module"],
                    "route": candidate["route"],
                }
                for candidate in matches
            ]

            return AgentAnswer(
                answer={
                    "status": "needs_clarification",
                    "intent": "navigate",
                    "screen": None,
                    "navigation_path": [],
                    "summary": (
                        "That still matches multiple screens. "
                        "Please be more specific."
                    ),
                    "candidates": candidate_data,
                    "steps": [],
                    "sources": [candidate["id"] for candidate in matches],
                },
                intent="navigate",
                sources=[],
            )

        # ---------------------------------------------------------
        # No match
        # ---------------------------------------------------------

        return AgentAnswer(
            answer={
                "status": "needs_clarification",
                "intent": "navigate",
                "screen": None,
                "navigation_path": [],
                "summary": (
                    "I couldn't match that to the available "
                    "navigation options. Please choose one of "
                    "the listed screens."
                ),
                "candidates": [
                    {
                        "id": candidate["id"],
                        "title": candidate["title"],
                        "module": candidate["module"],
                        "route": candidate["route"],
                    }
                    for candidate in candidates
                ],
                "steps": [],
                "sources": [candidate["id"] for candidate in candidates],
            },
            intent="navigate",
            sources=[],
        )

    def respond(
        self,
        question: str,
        history: list | None = None,
        conversation_id: str | None = None,
        current_screen: str | None = None,
    ) -> str:

        answer = self.answer(
            question=question,
            history=history,
            current_screen=current_screen,
            conversation_id=conversation_id,
        ).answer

        return (
            json.dumps(
                answer,
                ensure_ascii=False,
            )
            if isinstance(answer, dict)
            else answer
        )
