"""ActionRegistry — only explicitly registered handlers may execute."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.enums import ActionType
from app.resolution.context import ActionExecutionContext
from app.resolution.contracts import (
    ActionParameters,
    ActionResult,
    parameter_model_for,
    parse_action_parameters,
)


class ActionHandler(ABC):
    """Contract for a registered resolution action handler."""

    action_type: ActionType
    description: str
    requires_approval: bool = True

    @property
    def parameter_schema(self) -> type[ActionParameters]:
        return parameter_model_for(self.action_type)

    def validate_parameters(self, parameters: dict[str, Any]) -> ActionParameters:
        return parse_action_parameters(self.action_type, parameters)

    def describe(self) -> dict[str, Any]:
        """Inspectable metadata for callers (no executable payloads)."""
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "requires_approval": self.requires_approval,
            "parameter_schema": self.parameter_schema.__name__,
            "parameters_json_schema": self.parameter_schema.model_json_schema(),
        }

    @abstractmethod
    def execute(
        self,
        parameters: ActionParameters,
        context: ActionExecutionContext,
    ) -> ActionResult:
        """Run the action with typed parameters and session context."""


class ActionRegistry:
    """Maps action types to handlers. Unknown types cannot execute."""

    def __init__(self) -> None:
        self._handlers: dict[ActionType, ActionHandler] = {}

    def register(self, action_type: ActionType, handler: ActionHandler) -> None:
        if handler.action_type != action_type:
            raise ValueError(
                f"Handler action_type {handler.action_type.value} does not match "
                f"registration key {action_type.value}."
            )
        self._handlers[action_type] = handler

    def get(self, action_type: ActionType | str) -> ActionHandler:
        if isinstance(action_type, str):
            try:
                action_type = ActionType(action_type)
            except ValueError as exc:
                raise KeyError(f"Unknown action type: {action_type}") from exc
        try:
            return self._handlers[action_type]
        except KeyError as exc:
            raise KeyError(f"Action type not registered: {action_type.value}") from exc

    def list_available(self) -> list[ActionType]:
        return sorted(self._handlers.keys(), key=lambda t: t.value)

    def list_metadata(self) -> list[dict[str, Any]]:
        return [self.get(t).describe() for t in self.list_available()]

    def is_registered(self, action_type: ActionType | str) -> bool:
        try:
            self.get(action_type)
            return True
        except KeyError:
            return False


def build_default_registry() -> ActionRegistry:
    """Return a registry with the four M8.2 safe workflow handlers registered."""
    from app.resolution.handlers.escalate import EscalateToManagerHandler
    from app.resolution.handlers.missing_document import RequestMissingDocumentHandler
    from app.resolution.handlers.route_to_review import RouteToReviewHandler
    from app.resolution.handlers.vendor_clarification import (
        RequestVendorClarificationHandler,
    )

    registry = ActionRegistry()
    for handler in (
        RouteToReviewHandler(),
        RequestVendorClarificationHandler(),
        RequestMissingDocumentHandler(),
        EscalateToManagerHandler(),
    ):
        registry.register(handler.action_type, handler)
    return registry
