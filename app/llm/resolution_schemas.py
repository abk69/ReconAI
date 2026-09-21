"""M8.3 AI resolution planner schemas (Gemini wire + API).

The model proposes registered actions only. Application code validates,
persists, and later executes — Gemini never executes.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PlannerDecisionStatus = Literal["ACTIONS_PROPOSED", "NO_ACTION_RECOMMENDED"]

# Explicit enum for Gemini — must match ActionType values.
PlannerActionType = Literal[
    "ROUTE_TO_REVIEW",
    "REQUEST_VENDOR_CLARIFICATION",
    "REQUEST_MISSING_DOCUMENT",
    "ESCALATE_TO_MANAGER",
]


class PlannerProposedAction(BaseModel):
    """One proposed workflow action from the Gemini planner (pre-contract validation)."""

    model_config = ConfigDict(extra="forbid")

    action_type: PlannerActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    action_order: int = Field(ge=0, le=32)
    rationale: str = Field(min_length=1, max_length=4000)
    requires_approval: bool = True


class ResolutionPlannerGeminiOutput(BaseModel):
    """Strict structured output requested from Gemini for resolution planning."""

    model_config = ConfigDict(extra="forbid")

    status: PlannerDecisionStatus
    reasoning_summary: str = Field(min_length=1, max_length=8000)
    proposed_actions: list[PlannerProposedAction] = Field(default_factory=list, max_length=16)
    limitations: str = Field(default="", max_length=4000)


class ResolutionPlanCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_replan: bool = False
    policy_grounding_result_id: UUID | None = None


class ResolutionPlanningResponse(BaseModel):
    """API response for AI-generated resolution planning (never executes)."""

    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    exception_id: UUID
    status: str
    reasoning_summary: str
    limitations: str = ""
    policy_grounding_result_id: UUID | None = None
    planning_key: str | None = None
    planner_model: str | None = None
    prompt_version: str | None = None
    action_count: int
    actions: list[dict[str, Any]] = Field(default_factory=list)
    reused_existing: bool = False
    planning_latency_ms: int | None = None
