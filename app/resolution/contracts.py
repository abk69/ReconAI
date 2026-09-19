"""Typed action contracts for M8 resolution.

Arbitrary JSON is never treated as an executable action. Every payload must
match an explicit ``action_type`` discriminator and its parameter schema.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ActionType


class ActionParameters(BaseModel):
    """Base for typed action parameters (extra fields forbidden)."""

    model_config = ConfigDict(extra="forbid")


class RouteToReviewParameters(ActionParameters):
    """Parameters for ``ROUTE_TO_REVIEW``."""

    review_queue: str = Field(min_length=1, max_length=128)


class RequestVendorClarificationParameters(ActionParameters):
    """Parameters for ``REQUEST_VENDOR_CLARIFICATION``."""

    reason: str = Field(min_length=1, max_length=2000)
    fields: list[str] = Field(min_length=1, max_length=32)


class RequestMissingDocumentParameters(ActionParameters):
    """Parameters for ``REQUEST_MISSING_DOCUMENT``."""

    document_type: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class EscalateToManagerParameters(ActionParameters):
    """Parameters for ``ESCALATE_TO_MANAGER``."""

    manager_role: str = Field(min_length=1, max_length=128)
    urgency: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    summary: str = Field(min_length=1, max_length=2000)


class ActionRequest(BaseModel):
    """Discriminated action request — type selects the parameter schema."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    parameters: dict[str, Any]
    rationale: str = Field(default="", max_length=4000)
    requires_approval: bool | None = None


class ActionResult(BaseModel):
    """Normalized result returned by an action handler."""

    model_config = ConfigDict(extra="forbid")

    success: bool
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

