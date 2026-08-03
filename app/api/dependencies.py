from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.db import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class InMemoryRateLimiter:
    def __init__(self):
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def check(self, identity: str, limit: int) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=1)
        with self._lock:
            events = self._events[identity]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again shortly.",
                )
            events.append(now)


rate_limiter = InMemoryRateLimiter()


def authorize_request(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> str:
    settings = get_settings()
    allowed_keys = settings.allowed_api_keys
    if allowed_keys and x_api_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )
    if settings.environment.lower() == "production" and not allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )
    identity = x_api_key or (request.client.host if request.client else "anonymous")
    rate_limiter.check(identity, settings.rate_limit_per_minute)
    return identity
