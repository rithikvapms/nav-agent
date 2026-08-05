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
        self.retriever = Retriever(repository)
        self.llm = LLMService()
        self.understanding = QueryUnderstanding.from_chunks(
            repository.get_vocabulary_chunks(knowledge_source_id)
        )
        self.knowledge_source_id = knowledge_source_id
        self.graph = NavigationGraphService(db)

    def answer(
        self, question: str, history: list | None = None, current_screen: str | None = None
    ) -> AgentAnswer:
        input_result = SecurityGuard.check_input(question)
        if not input_result.allowed:
            return AgentAnswer(
                input_result.message or "I can't process that message.", "blocked", []
            )
        identity_result = IdentityGuard.check(input_result.text)

        if identity_result.handled:
            return AgentAnswer(
                answer=identity_result.answer,
                intent="identity",
                sources=[],
            )

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

        if intent == "chat":
            answer, token_usage = self.llm.generate(
                normalized_question, history, current_screen=current_screen
            )
            return AgentAnswer(SecurityGuard.sanitize_output(answer), intent, [], token_usage)

        retrieval_query = self.understanding.retrieval_query(
            normalized_question, intent
        )
        graph_path = (
            self.graph.find_path(
                self.knowledge_source_id,
                current_screen,
                normalized_question,
            )
            if self.knowledge_source_id is not None
            else []
        )
        retrieved_chunks = self.retriever.retrieve(
            retrieval_query, knowledge_source_id=self.knowledge_source_id
        )

        logger.info(
            "Retrieved %d chunks",
            len(retrieved_chunks),
        )
        
        prompt = build_rag_user_prompt(
            normalized_question, retrieved_chunks, intent, history, graph_path
        )
        sources, seen = [], set()
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
        answer, token_usage = self.llm.generate(prompt, current_screen=current_screen)
        safe_answer = SecurityGuard.sanitize_output(answer)
        if intent == "navigate":
            try:
                structured_answer = json.loads(safe_answer)
                if isinstance(structured_answer, dict):
                    return AgentAnswer(structured_answer, intent, sources, token_usage)
            except json.JSONDecodeError:
                logger.warning("Navigation response was not valid JSON")
            # Older prompt branches used plain text for clarification/not-found
            # navigation responses. Keep that content, but preserve the public
            # navigation contract as structured JSON.
            return AgentAnswer(
                {
                    "status": "success",
                    "intent": "navigate",
                    "screen": {"id": None, "title": None, "module": None},
                    "navigation_path": [],
                    "summary": safe_answer,
                    "steps": [],
                    "sources": [item["screen_id"] for item in sources],
                },
                intent,
                sources,
                token_usage,
            )
        return AgentAnswer(safe_answer, intent, sources, token_usage)

    def respond(self, question: str, history: list | None = None) -> str:
        """Compatibility method for earlier integrations."""
        answer = self.answer(question, history).answer
        return json.dumps(answer, ensure_ascii=False) if isinstance(answer, dict) else answer
