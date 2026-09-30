"""Local filesystem storage backend for development and tests."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from app.storage.base import StorageBackend, StorageError

_SAFE_EXTENSION = re.compile(r"^\.[a-z0-9]{1,16}$")


class LocalFileStorage(StorageBackend):
    """Store binaries under a configured root using UUID-based filenames."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def ensure_root(self) -> None:
        """Create the storage root directory if missing."""
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Unable to create storage directory: {self._root}") from exc

    def _resolve_safe_path(self, stored_filename: str) -> Path:
        """Resolve a stored filename under the root, rejecting path traversal."""
        if not stored_filename or stored_filename != Path(stored_filename).name:
            raise StorageError("Unsafe storage filename rejected.")
        if ".." in stored_filename or "/" in stored_filename or "\\" in stored_filename:
            raise StorageError("Unsafe storage filename rejected.")

        candidate = (self._root / stored_filename).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise StorageError("Path traversal attempt rejected.") from exc
        return candidate

    def save(self, *, document_id: UUID, extension: str, data: bytes) -> tuple[str, Path]:
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if not _SAFE_EXTENSION.match(ext):
            raise StorageError("Unsafe file extension rejected.")

        self.ensure_root()
        stored_filename = f"{document_id}{ext}"
        path = self._resolve_safe_path(stored_filename)
        try:
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"Failed to write document to storage: {path}") from exc
        return stored_filename, path

    def delete(self, *, stored_filename: str) -> None:
        path = self._resolve_safe_path(stored_filename)
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            raise StorageError(f"Failed to delete stored document: {path}") from exc

    def exists(self, *, stored_filename: str) -> bool:
        path = self._resolve_safe_path(stored_filename)
        return path.exists()

    def read(self, *, stored_filename: str) -> bytes:
        """Read stored binary content. Never exposes a user-controlled path."""
        path = self._resolve_safe_path(stored_filename)
        if not path.exists():
            raise StorageError(f"Stored document not found: {stored_filename}")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError(f"Failed to read stored document: {stored_filename}") from exc
