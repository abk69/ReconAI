"""Operational logs. Messages stay free of secrets and document text."""

from __future__ import annotations

import logging

from app.core.request_context import current_request_id

logger = logging.getLogger("app.http")


def _request_id() -> str:
    return current_request_id() or "-"


def log_request(*, method: str, path: str, status_code: int, duration_ms: float) -> None:
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.3f request_id=%s",
        method,
        path,
        status_code,
        duration_ms,
        _request_id(),
    )


def log_application_error() -> None:
    logger.error("application_error request_id=%s", _request_id())


def log_database_not_ready() -> None:
    logger.error("database_not_ready request_id=%s", _request_id())


def log_provider_failure(category: str) -> None:
    logger.warning("provider_failure category=%s request_id=%s", category, _request_id())
