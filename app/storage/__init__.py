"""Storage backends for document binaries."""

from app.storage.base import StorageBackend, StorageError
from app.storage.local import LocalFileStorage

__all__ = [
    "LocalFileStorage",
    "StorageBackend",
    "StorageError",
]
