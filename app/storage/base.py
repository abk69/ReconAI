"""Abstract storage backend for document binaries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID


class StorageError(Exception):
    """Raised when a storage operation fails."""


class StorageBackend(ABC):
    """Interface for persisting uploaded file bytes outside the database."""

    @abstractmethod
    def save(self, *, document_id: UUID, extension: str, data: bytes) -> tuple[str, Path]:
        """Persist bytes and return ``(stored_filename, absolute_path)``."""

    @abstractmethod
    def delete(self, *, stored_filename: str) -> None:
        """Remove a previously stored object if it exists."""

    @abstractmethod
    def exists(self, *, stored_filename: str) -> bool:
        """Return whether the stored object exists."""

    @abstractmethod
    def read(self, *, stored_filename: str) -> bytes:
        """Return raw bytes for a previously stored object."""
