import hashlib
import json

from openai import OpenAI

from app.cache.response_cache import response_cache
from app.core.config import get_settings
from app.core.logger import logger
from app.prompts.system import SYSTEM_PROMPT
from app.utils.retry import retry


class LLMService:

    def __init__(self):

        settings = get_settings()

        self.client = OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=30,
        )

        self.model = settings.groq_model
        self.temperature = 0.2
        self.max_tokens = 1024

    def generate(
        self, prompt: str, history: list | None = None, current_screen: str | None = None
    ) -> tuple[str, int]:

        history = history or []

        cache_payload = {
            "prompt": prompt,
            "history": history[-8:],
            "model": self.model,
            "current_screen": current_screen,
        }

        cache_key = hashlib.sha256(
            json.dumps(cache_payload, sort_keys=True).encode()
        ).hexdigest()

        # ---------- Cache ----------
        if cache_key in response_cache:
            logger.info("Response Cache HIT")
            cached = response_cache[cache_key]
            if isinstance(cached, dict):
                return cached["answer"], 0
            return cached, 0

        logger.info("Response Cache MISS")

        try:

            logger.info(
                "Sending request to Groq | Model=%s",
                self.model,
            )

            response = retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{
                        "role": "system",
                        "content": (
                            f"{SYSTEM_PROMPT}\n\n"
                            f"Current user screen: {current_screen or 'Unknown'}. "
                            "Use this only as navigation context; do not claim a screen change."
                        ),
                    }]
                    + [
                        {
                            "role": item["role"],
                            "content": item["content"],
                        }
                        for item in history[-8:]
                        if item.get("role") in {"user", "assistant"}
                        and item.get("content")
                    ]
                    + [{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            )

            answer = response.choices[0].message.content.strip()

            token_usage = getattr(response.usage, "total_tokens", 0) or 0
            response_cache[cache_key] = {"answer": answer, "token_usage": token_usage}

            logger.info("Groq response received successfully")

            return answer, token_usage

        except Exception:
            logger.exception("Groq request failed")
            raise
