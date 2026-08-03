import time
from typing import Callable, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)

from app.core.logger import logger

T = TypeVar("T")


def retry(
    func: Callable[[], T],
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
) -> T:

    current_delay = delay

    for attempt in range(retries):

        try:
            return func()

        except (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        ) as e:

            if attempt == retries - 1:
                logger.error(
                    "LLM request failed after %d attempts",
                    retries,
                )
                raise

            logger.warning(
                "Retry %d/%d after %s",
                attempt + 1,
                retries,
                type(e).__name__,
            )

            time.sleep(current_delay)
            current_delay *= backoff
