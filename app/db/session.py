"""SQLAlchemy engine and session helpers."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    """Ensure SQLite enforces foreign keys (disabled by default)."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@lru_cache
def get_engine() -> Engine:
    """Create (and cache) the application SQLAlchemy engine."""
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if settings.database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached session factory bound to the application engine."""
    return sessionmaker(
        bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI-compatible dependency that yields a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
