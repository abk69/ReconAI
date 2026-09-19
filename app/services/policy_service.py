"""Policy knowledge-base service (M7.1) — no embeddings or retrieval."""

from __future__ import annotations

import hashlib
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import PolicyChunk, PolicyDocument, PolicyVersion
from app.domain.enums import PolicyVersionStatus


class PolicyServiceError(Exception):
    """Base policy service error."""


class PolicyNotFoundError(PolicyServiceError):
    """Referenced policy entity does not exist."""


class PolicyConflictError(PolicyServiceError):
    """Uniqueness / integrity conflict."""


class PolicyValidationError(PolicyServiceError):
    """Invalid policy input."""


def content_sha256(text: str) -> str:
    """Deterministic SHA-256 hex digest for provenance/content identity."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PolicyService:
    """CRUD for policy documents, versions, and chunks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- Policy documents -----------------------------------------------------

    def create_document(self, *, name: str, description: str | None = None) -> PolicyDocument:
        name = name.strip()
        if not name:
            raise PolicyValidationError("Policy document name is required.")
        existing = self._session.scalar(select(PolicyDocument).where(PolicyDocument.name == name))
        if existing is not None:
            raise PolicyConflictError(f"Policy document named {name!r} already exists.")
        doc = PolicyDocument(name=name, description=description)
        self._session.add(doc)
        self._session.commit()
        return doc

    def list_documents(self) -> list[PolicyDocument]:
        return list(
            self._session.scalars(select(PolicyDocument).order_by(PolicyDocument.name)).all()
        )

    def get_document(self, policy_id: UUID) -> PolicyDocument:
        doc = self._session.get(PolicyDocument, policy_id)
        if doc is None:
            raise PolicyNotFoundError(f"Policy document {policy_id} was not found.")
        return doc

    # --- Versions -------------------------------------------------------------

    def create_version(
        self,
        policy_id: UUID,
        *,
        version_label: str,
        effective_from: date,
        title: str | None = None,
        status: PolicyVersionStatus = PolicyVersionStatus.DRAFT,
        effective_to: date | None = None,
        source_filename: str | None = None,
        source_reference: str | None = None,
        source_content: str | None = None,
        content_hash: str | None = None,
    ) -> PolicyVersion:
        doc = self.get_document(policy_id)
        label = version_label.strip()
        if not label:
            raise PolicyValidationError("version_label is required.")
        if effective_to is not None and effective_to < effective_from:
            raise PolicyValidationError("effective_to cannot be before effective_from.")

        digest = content_hash
        if digest is None:
            if source_content is None:
                raise PolicyValidationError(
                    "Provide content_hash or source_content to fingerprint the version."
                )
            digest = content_sha256(source_content)
        elif len(digest) != 64:
            raise PolicyValidationError("content_hash must be a 64-character SHA-256 hex digest.")

        version = PolicyVersion(
            policy_document_id=doc.id,
            version_label=label,
            title=title,
            status=status.value,
            effective_from=effective_from,
            effective_to=effective_to,
            source_filename=source_filename,
            source_reference=source_reference,
            content_hash=digest,
        )
        self._session.add(version)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise PolicyConflictError(
                f"Version label {label!r} already exists for this policy document."
            ) from exc
        return self.get_version(policy_id, version.id)

    def list_versions(self, policy_id: UUID) -> list[PolicyVersion]:
        self.get_document(policy_id)
        return list(
            self._session.scalars(
                select(PolicyVersion)
                .where(PolicyVersion.policy_document_id == policy_id)
                .order_by(PolicyVersion.effective_from.desc(), PolicyVersion.created_at.desc())
            ).all()
        )

    def get_version(self, policy_id: UUID, version_id: UUID) -> PolicyVersion:
        self.get_document(policy_id)
        version = self._session.scalar(
            select(PolicyVersion)
            .where(
                PolicyVersion.id == version_id,
                PolicyVersion.policy_document_id == policy_id,
            )
            .options(selectinload(PolicyVersion.chunks))
            .execution_options(populate_existing=True)
        )
        if version is None:
            raise PolicyNotFoundError(
                f"Policy version {version_id} was not found for document {policy_id}."
            )
        return version

    # --- Chunks ---------------------------------------------------------------

    def add_chunks(
        self,
        policy_id: UUID,
        version_id: UUID,
        chunks: list[dict[str, object]],
    ) -> list[PolicyChunk]:
        version = self.get_version(policy_id, version_id)
        if not chunks:
            raise PolicyValidationError("At least one chunk is required.")

        created: list[PolicyChunk] = []
        for item in chunks:
            index = int(item["chunk_index"])  # type: ignore[arg-type]
            if index < 0:
                raise PolicyValidationError("chunk_index must be >= 0.")
            content = str(item["content"])
            if not content.strip():
                raise PolicyValidationError("chunk content cannot be empty.")
            digest = item.get("content_hash")
            if digest is None:
                digest = content_sha256(content)
            else:
                digest = str(digest)
                if len(digest) != 64:
                    raise PolicyValidationError(
                        "content_hash must be a 64-character SHA-256 hex digest."
                    )
            page = item.get("page_number")
            created.append(
                PolicyChunk(
                    policy_version_id=version.id,
                    chunk_index=index,
                    section_id=(str(item["section_id"]) if item.get("section_id") else None),
                    section_title=(
                        str(item["section_title"]) if item.get("section_title") else None
                    ),
                    content=content,
                    content_hash=digest,
                    source_filename=(
                        str(item["source_filename"]) if item.get("source_filename") else None
                    ),
                    page_number=int(page) if page is not None else None,
                )
            )

        self._session.add_all(created)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise PolicyConflictError("Duplicate chunk_index for this policy version.") from exc

        return self.list_chunks(policy_id, version_id)

    def list_chunks(self, policy_id: UUID, version_id: UUID) -> list[PolicyChunk]:
        self.get_version(policy_id, version_id)
        return list(
            self._session.scalars(
                select(PolicyChunk)
                .where(PolicyChunk.policy_version_id == version_id)
                .order_by(PolicyChunk.chunk_index)
            ).all()
        )
