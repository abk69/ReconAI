"""M8 controlled agentic resolution — plans, typed actions, guardrails.

M8.1 provides architecture and persistence only. No LLM agent execution.
"""

from app.resolution.contracts import (
    ActionParameters,
    ActionRequest,
    ActionResult,
    EscalateToManagerParameters,
    RequestMissingDocumentParameters,
    RequestVendorClarificationParameters,
    RouteToReviewParameters,
    parse_action_request,
)
from app.resolution.registry import ActionHandler, ActionRegistry, build_default_registry

__all__ = [
    "ActionHandler",
    "ActionParameters",
    "ActionRegistry",
    "ActionRequest",
    "ActionResult",
    "EscalateToManagerParameters",
    "RequestMissingDocumentParameters",
    "RequestVendorClarificationParameters",
    "RouteToReviewParameters",
    "build_default_registry",
    "parse_action_request",
]
