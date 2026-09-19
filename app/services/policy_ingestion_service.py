"""Policy source ingestion — deterministic parse + chunk + persist (M7.2)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import PolicyChunk
from app.policy.chunking import chunk_sections
from app.policy.markdown import parse_markdown
from app.policy.pdf import PolicyPdfError, parse_pdf
from app.services.policy_service import (
    PolicyConflictError,
    PolicyService,
    PolicyValidationError,
)

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".pdf"}


@dataclass(frozen=True)
class IngestionResult:
    policy_id: UUID
    version_id: UUID
    source_hash: str
    chunks_created: int
    status: str  # INGESTED | ALREADY_INGESTED
    message: str | None = None


class PolicyIngestionService:
    """Ingest Markdown/PDF policy sources into an existing PolicyVersion."""

    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._policies = PolicyService(session)

    def ingest(
        self,
        policy_id: UUID,
        version_id: UUID,
        *,
        filename: str | None,
        data: bytes,
    ) -> IngestionResult:
        if not data:
            raise PolicyValidationError("Policy source file is empty.")
        if len(data) > self._settings.max_policy_upload_bytes:
            raise PolicyValidationError(
                f"Policy source exceeds max size "
                f"({self._settings.max_policy_upload_bytes} bytes)."
            )

        ext = Path(filename or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise PolicyValidationError(
                f"Unsupported policy source type {ext!r}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
            )

        source_hash = hashlib.sha256(data).hexdigest()
        safe_name = Path(filename or f"policy{ext}").name
        version = self._policies.get_version(policy_id, version_id)

        existing = list(version.chunks)
        if existing:
            if version.content_hash == source_hash:
                return IngestionResult(
                    policy_id=policy_id,
                    version_id=version_id,
                    source_hash=source_hash,
                    chunks_created=len(existing),
                    status="ALREADY_INGESTED",
                    message="Identical source already ingested; returning existing chunks.",
                )
            raise PolicyConflictError(
                "Policy version already has chunks from a different source. "
                "Create a new version to re-ingest."
            )

        try:
            parsed = self._parse(ext=ext, data=data, filename=safe_name)
        except PolicyPdfError as exc:
            raise PolicyValidationError(str(exc)) from exc

        prepared = chunk_sections(
            parsed,
            max_chars=self._settings.policy_chunk_max_chars,
        )
        if not prepared:
            raise PolicyValidationError(
                "No policy chunks could be produced from the source document."
            )

        # Single transaction: update version fingerprint + insert all chunks.
        version.content_hash = source_hash
        version.source_filename = safe_name
        for item in prepared:
            self._session.add(
                PolicyChunk(
                    policy_version_id=version.id,
                    chunk_index=item.chunk_index,
                    section_id=item.section_id,
                    section_title=item.section_title,
                    content=item.content,
                    content_hash=item.content_hash,
                    source_filename=item.source_filename or safe_name,
                    page_number=item.page_number,
                )
            )
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return IngestionResult(
            policy_id=policy_id,
            version_id=version_id,
            source_hash=source_hash,
            chunks_created=len(prepared),
            status="INGESTED",
            message="Policy source ingested and chunked.",
        )

    def _parse(self, *, ext: str, data: bytes, filename: str):
        if ext in {".md", ".markdown"}:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PolicyValidationError(
                    "Markdown policy sources must be UTF-8 encoded."
                ) from exc
            return parse_markdown(text, source_filename=filename)
        if ext == ".pdf":
            return parse_pdf(data, source_filename=filename)
        raise PolicyValidationError(f"Unsupported policy source type {ext!r}.")
