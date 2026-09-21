"""Database package exports."""

# Register ORM mappers, then enable immutability / audit guards.
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db, get_engine, get_session_factory
from app.resolution.audit import register_resolution_audit_immutability
from app.resolution.immutability import register_proposed_action_immutability

register_proposed_action_immutability()
register_resolution_audit_immutability()

__all__ = [
    "Base",
    "get_db",
    "get_engine",
    "get_session_factory",
]
