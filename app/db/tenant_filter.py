"""Apply the current tenant to ORM reads and stamp it onto new rows."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, with_loader_criteria

from app.db.base import Base

_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("tenant_id", default=None)
_suspended: ContextVar[bool] = ContextVar("tenant_filter_suspended", default=False)
_installed = False


def current_tenant_id() -> uuid.UUID | None:
    return _tenant_id.get()


def set_tenant_id(value: uuid.UUID | None) -> Token[uuid.UUID | None]:
    return _tenant_id.set(value)


def reset_tenant_id(token: Token[uuid.UUID | None]) -> None:
    _tenant_id.reset(token)


@contextmanager
def suspend_tenant_filter() -> Iterator[None]:
    """Read across tenants. Callers must set the job tenant before business writes."""
    token = _suspended.set(True)
    try:
        yield
    finally:
        _suspended.reset(token)


def _scoped_classes() -> list[type]:
    classes: list[type] = []
    for mapper in Base.registry.mappers:
        if "tenant_id" in mapper.attrs:
            classes.append(mapper.class_)
    return classes


def install_tenant_filter() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    _install_identity_map_guard()

    @event.listens_for(Session, "do_orm_execute")
    def _apply_tenant(execute_state):  # type: ignore[no-untyped-def]
        if not execute_state.is_select:
            return
        if execute_state.execution_options.get("skip_tenant_filter"):
            return
        if _suspended.get():
            return
        tenant_id = _tenant_id.get()
        # No tenant means an internal session (migrations, offline evaluation,
        # or the worker before it binds a job). Protected HTTP handlers set
        # the tenant before they run, and that context hides every other tenant.
        if tenant_id is None:
            return
        classes = _scoped_classes()
        if not classes:
            return

        # Close over the tenant so the query cache does not reuse another
        # tenant's compiled statement. A default argument is not tracked.
        def _criteria(cls):  # type: ignore[no-untyped-def]
            return cls.tenant_id == tenant_id

        for cls in classes:
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(cls, _criteria, include_aliases=True)
            )

    @event.listens_for(Session, "before_flush")
    def _stamp_tenant(session, flush_context, instances):  # type: ignore[no-untyped-def]
        del flush_context, instances
        tenant_id = _tenant_id.get()
        if tenant_id is None:
            return
        for obj in session.new:
            if "tenant_id" in obj.__mapper__.attrs and getattr(obj, "tenant_id", None) is None:
                obj.tenant_id = tenant_id


def _install_identity_map_guard() -> None:
    """Session.get returns cached instances before SQL, so the loader criteria never run.

    A request uses a new session, and the worker expires its session before each job.
    This guard still refuses a cached row when the bound tenant does not own it.
    """
    original_get = Session.get

    def _get(self: Session, entity: object, ident: object, **kwargs: object) -> object:
        instance = original_get(self, entity, ident, **kwargs)  # type: ignore[arg-type]
        if instance is None or _suspended.get():
            return instance
        tenant_id = _tenant_id.get()
        if tenant_id is None:
            return instance
        if "tenant_id" not in inspect(instance).mapper.attrs:
            return instance
        if getattr(instance, "tenant_id", None) != tenant_id:
            return None
        return instance

    Session.get = _get  # type: ignore[method-assign]
