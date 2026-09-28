"""Per-request correlation id. This is not an authentication credential."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_LENGTH = 128
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def resolve_request_id(raw: str | None) -> str:
    """Echo a short safe client id, or generate a new UUID."""
    if raw is None:
        return str(uuid4())
    candidate = raw.strip()
    if not candidate or len(candidate) > _MAX_LENGTH or _SAFE_ID.fullmatch(candidate) is None:
        return str(uuid4())
    return candidate
