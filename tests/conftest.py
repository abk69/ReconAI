"""Shared fixtures for isolated database tests.

ORM tests use an in-memory SQLite database so they never touch a developer
or production PostgreSQL instance. Production models still target PostgreSQL
(JSONB via dialect variants, UUID, Numeric, timezone-aware timestamps).

Alembic upgrade tests use a temporary on-disk SQLite file with the same
portable schema (JSONB → JSON variant).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401 — register mappers
from app.db.base import Base


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def sqlite_engine() -> Generator[Engine, None, None]:
    """Yield an isolated in-memory SQLite engine with FKs enabled."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Generator[Session, None, None]:
    """Yield a transactional session bound to the isolated test engine."""
    factory = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Configure Alembic against a temporary SQLite database URL."""
    db_path = tmp_path / "reconai_alembic.db"
    url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)

    # Settings and engines may already be cached from other imports.
    from app.core.config import get_settings
    from app.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


@pytest.fixture
def migrated_engine(alembic_config: Config) -> Generator[Engine, None, None]:
    """Run Alembic upgrade head and yield an engine against that schema."""
    command.upgrade(alembic_config, "head")
    url = alembic_config.get_main_option("sqlalchemy.url")
    assert url is not None
    engine = create_engine(url)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    yield engine
    engine.dispose()


def assert_table_exists(engine: Engine, table_name: str) -> None:
    """Helper for migration assertions."""
    assert table_name in inspect(engine).get_table_names()
