"""M7.4 grounded policy reasoning schemas (Gemini wire + API)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PolicyGroundingStatus(StrEnum):
    """Outcome of grounded policy explanation (not M2 reconciliation status)."""

    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_POLICY = "CONFLICTING_POLICY"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class GroundedPolicyGeminiOutput(BaseModel):
    """Strict structured output requested from Gemini for policy grounding.

    Citations are chunk UUID strings that MUST appear in the retrieved allowlist.
    Application code expands them into full provenance — Gemini must not invent IDs.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["SUPPORTED", "INSUFFICIENT_EVIDENCE", "CONFLICTING_POLICY"]
    conclusion: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    policy_support: str = Field(default="")
    cited_chunk_ids: list[str] = Field(default_factory=list)
    limitations: str = Field(default="")


class PolicyCitation(BaseModel):
    """Application-validated citation with provenance from retrieved chunks only."""

    model_config = ConfigDict(extra="forbid")

    policy_document_id: UUID
    policy_version_id: UUID
    policy_version_label: str
    chunk_id: UUID
    chunk_index: int
    section_id: str | None = None
    section_title: str | None = None
    source_filename: str | None = None
    page_number: int | None = None
    content_hash: str
    similarity: float | None = None


class GroundedPolicyResponse(BaseModel):
    """Final grounded explanation returned to API clients (AI-derived, not M2 truth)."""

    model_config = ConfigDict(extra="forbid")

    exception_id: UUID
    status: PolicyGroundingStatus
    conclusion: str
    explanation: str
    policy_support: str = ""
    citations: list[PolicyCitation] = Field(default_factory=list)
    limitations: str = ""
    retrieval_query: str
    retrieved_chunk_ids: list[UUID] = Field(default_factory=list)
    model: str | None = None
    grounding_result_id: UUID | None = None


class PolicyExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version_id: UUID | None = None
    policy_document_id: UUID | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    persist: bool = True


class PolicyExplanationResponse(GroundedPolicyResponse):
    """HTTP response for POST …/policy-explanation."""

    exception_type: str | None = None
    exception_status: str | None = None
    reconciliation_evidence: dict[str, Any] = Field(default_factory=dict)
