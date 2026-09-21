"""Typed action contracts for M8 resolution.

Arbitrary JSON is never treated as an executable action. Every payload must
match an explicit ``action_type`` discriminator and its parameter schema.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import ActionType, EscalationPriority


class ActionParameters(BaseModel):
    """Base for typed action parameters (extra fields forbidden)."""

    model_config = ConfigDict(extra="forbid")


class RouteToReviewParameters(ActionParameters):
    """Parameters for ``ROUTE_TO_REVIEW``."""

    review_queue: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=2000)
    assigned_to: str | None = Field(default=None, max_length=255)
    # Optional M5 link when a document extraction already exists.
    document_id: UUID | None = None
    extraction_result_id: UUID | None = None

    @field_validator("review_queue", "reason", "assigned_to")
    @classmethod
    def _strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped

    @model_validator(mode="after")
    def _document_pair(self) -> RouteToReviewParameters:
        if (self.document_id is None) ^ (self.extraction_result_id is None):
            raise ValueError(
                "document_id and extraction_result_id must both be provided or both omitted."
            )
        return self


class RequestVendorClarificationParameters(ActionParameters):
    """Parameters for ``REQUEST_VENDOR_CLARIFICATION``."""

    question: str = Field(min_length=1, max_length=4000)
    vendor_id: UUID | None = None
    vendor_reference: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=2000)
    fields: list[str] = Field(default_factory=list, max_length=32)
    due_date: date | None = None

    @field_validator("question", "vendor_reference", "reason")
    @classmethod
    def _strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped

    @field_validator("fields")
    @classmethod
    def _clean_fields(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("fields entries must not be empty")
            if len(text) > 128:
                raise ValueError("fields entries must be at most 128 characters")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def _require_vendor(self) -> RequestVendorClarificationParameters:
        if self.vendor_id is None and not self.vendor_reference:
            raise ValueError("Either vendor_id or vendor_reference is required.")
        return self


class RequestMissingDocumentParameters(ActionParameters):
    """Parameters for ``REQUEST_MISSING_DOCUMENT``."""

    document_type: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)
    vendor_id: UUID | None = None
    vendor_reference: str | None = Field(default=None, max_length=255)

    @field_validator("document_type", "reason", "vendor_reference")
    @classmethod
    def _strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped


class EscalateToManagerParameters(ActionParameters):
    """Parameters for ``ESCALATE_TO_MANAGER``."""

    reason: str = Field(min_length=1, max_length=2000)
    priority: EscalationPriority = EscalationPriority.MEDIUM
    destination: str | None = Field(default=None, max_length=128)

    @field_validator("reason", "destination")
    @classmethod
    def _strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace")
        return stripped


class ActionRequest(BaseModel):
    """Discriminated action request — type selects the parameter schema.

    ``requires_approval`` on the request is ignored at persistence time; the
    ActionRegistry handler definition is authoritative (M8.4).
    """

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    parameters: dict[str, Any]
    rationale: str = Field(default="", max_length=4000)
    requires_approval: bool | None = None


class ActionResult(BaseModel):
    """Normalized structured result returned by an action handler."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    status: Literal["created", "already_exists", "failed"] = "created"
    reference_id: UUID | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


_PARAMETER_MODELS: dict[ActionType, type[ActionParameters]] = {
    ActionType.ROUTE_TO_REVIEW: RouteToReviewParameters,
    ActionType.REQUEST_VENDOR_CLARIFICATION: RequestVendorClarificationParameters,
    ActionType.REQUEST_MISSING_DOCUMENT: RequestMissingDocumentParameters,
    ActionType.ESCALATE_TO_MANAGER: EscalateToManagerParameters,
}


def parameter_model_for(action_type: ActionType) -> type[ActionParameters]:
    """Return the Pydantic parameter model for a registered action type."""
    try:
        return _PARAMETER_MODELS[action_type]
    except KeyError as exc:
        raise ValueError(f"Unknown action type: {action_type}") from exc


def parse_action_parameters(
    action_type: ActionType | str,
    parameters: dict[str, Any],
) -> ActionParameters:
    """Validate raw parameters against the typed schema for ``action_type``."""
    if isinstance(action_type, str):
        try:
            action_type = ActionType(action_type)
        except ValueError as exc:
            raise ValueError(f"Unknown action type: {action_type}") from exc
    model = parameter_model_for(action_type)
    return model.model_validate(parameters)


def parse_action_request(payload: dict[str, Any] | ActionRequest) -> ActionRequest:
    """Parse and validate an action request; parameters must match the type."""
    request = (
        payload
        if isinstance(payload, ActionRequest)
        else ActionRequest.model_validate(payload)
    )
    parse_action_parameters(request.action_type, request.parameters)
    return request
