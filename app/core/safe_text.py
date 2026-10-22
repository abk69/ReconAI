"""Strip filesystem paths and secrets from messages returned to API clients."""

from __future__ import annotations

import re

_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s'\"`,;:]+)+")
_SECRET = re.compile(
    r"(api[_-]?key|authorization|bearer\s+\S+|password|secret|database_url)",
    re.IGNORECASE,
)


def sanitize_public_message(message: str | None, *, fallback: str) -> str:
    """Return a short client-safe sentence, or ``fallback`` when the text is unsafe."""
    if not message:
        return fallback
    text = " ".join(str(message).split())
    if not text:
        return fallback
    if _SECRET.search(text) or _PATH.search(text):
        return fallback
    if len(text) > 180:
        return fallback
    return text
