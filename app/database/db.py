from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def init_database() -> None:
    """Create application-owned tables when they do not already exist."""
    import app.models.chat_message  # noqa: F401
    import app.models.knowledge_source  # noqa: F401
    import app.models.screen_chunk  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # create_all does not add new columns to an existing table. Keep this
    # lightweight migration for installations created before token tracking.
    columns = {column["name"] for column in inspect(engine).get_columns("chat_messages")}
    if "token_usage" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE chat_messages ADD COLUMN token_usage BIGINT NOT NULL DEFAULT 0")
            )
