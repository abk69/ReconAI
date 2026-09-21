"""Database package exports."""

# Register ORM mappers, then enable ProposedAction immutability guards.
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db, get_engine, get_session_factory
from app.resolution.immutability import register_proposed_action_immutability

register_proposed_action_immutability()

__all__ = [
    "Base",
    "get_db",
    "get_engine",
    "get_session_factory",
]
