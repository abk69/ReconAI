"""ActionRegistry — only explicitly registered handlers may execute."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.enums import ActionType
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

    @abstractmethod
    def execute(self, parameters: ActionParameters) -> ActionResult:
        """Run the action. M8.1 handlers are safe placeholders only."""


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

    def is_registered(self, action_type: ActionType | str) -> bool:
        try:
            self.get(action_type)
            return True
        except KeyError:
            return False


class _PlaceholderHandler(ActionHandler):
    """Safe no-op handler used until a later milestone adds real side effects."""

    def __init__(
        self,
        action_type: ActionType,
        description: str,
        *,
        requires_approval: bool = True,
    ) -> None:
        self.action_type = action_type
        self.description = description
        self.requires_approval = requires_approval

    def execute(self, parameters: ActionParameters) -> ActionResult:
        return ActionResult(
            success=True,
            message=f"Placeholder execution for {self.action_type.value}",
            data={"action_type": self.action_type.value, "parameters": parameters.model_dump()},
        )


def build_default_registry() -> ActionRegistry:
    """Return a registry with the four M8.1 workflow actions registered."""
    registry = ActionRegistry()
    specs: list[tuple[ActionType, str, bool]] = [
        (
            ActionType.ROUTE_TO_REVIEW,
            "Route the exception to a human review queue.",
            True,
        ),
        (
            ActionType.REQUEST_VENDOR_CLARIFICATION,
            "Request clarification from the vendor on disputed fields.",
            True,
        ),
        (
            ActionType.REQUEST_MISSING_DOCUMENT,
            "Request a missing supporting document.",
            True,
        ),
        (
            ActionType.ESCALATE_TO_MANAGER,
            "Escalate the exception to a manager role.",
            True,
        ),
    ]
    for action_type, description, requires_approval in specs:
        registry.register(
            action_type,
            _PlaceholderHandler(
                action_type,
                description,
                requires_approval=requires_approval,
            ),
        )
    return registry
