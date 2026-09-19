"""Gemini-compatible JSON Schema helpers for structured output.

Pydantic ``extra='forbid'`` emits JSON Schema ``additionalProperties: false``.
The Gemini API rejects that keyword in ``generation_config.response_schema``.
We keep strict Pydantic models for *application* validation and strip
unsupported keywords only from the wire schema sent to Gemini.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

# Keywords Gemini's response_schema proto does not accept in practice.
_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "additionalProperties",
        "additional_properties",
    }
)


def strip_unsupported_schema_keys(node: Any) -> Any:
    """Recursively remove Gemini-unsupported JSON Schema keywords."""
    if isinstance(node, dict):
        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in _UNSUPPORTED_SCHEMA_KEYS:
                continue
            cleaned[key] = strip_unsupported_schema_keys(value)
        return cleaned
    if isinstance(node, list):
        return [strip_unsupported_schema_keys(item) for item in node]
    return node


def schema_contains_additional_properties(node: Any) -> bool:
    """Return True if any object in the schema tree has additionalProperties."""
    if isinstance(node, dict):
        if "additionalProperties" in node or "additional_properties" in node:
            return True
        return any(schema_contains_additional_properties(v) for v in node.values())
    if isinstance(node, list):
        return any(schema_contains_additional_properties(item) for item in node)
    return False


def gemini_response_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Build a Gemini-safe JSON Schema from a Pydantic model.

    Application models may still use ``extra='forbid'``; that constraint is
    enforced when we ``model_validate`` the provider response, not via the
    wire schema.
    """
    raw = model.model_json_schema()
    return strip_unsupported_schema_keys(deepcopy(raw))
