"""Deterministic fake resolution planner for M8.7 offline evaluation."""

from __future__ import annotations

from typing import Any

from app.evaluation.m8_golden import PlannerSimMode, ResolutionEvalCase
from app.llm.base import LLMProviderError, LLMUsageMetadata, StructuredLLMResponse
from app.llm.resolution_schemas import ResolutionPlannerGeminiOutput


def _valid_route(**overrides: Any) -> dict[str, Any]:
    data = {
        "status": "ACTIONS_PROPOSED",
        "reasoning_summary": "Route exception for human procurement review.",
        "proposed_actions": [
            {
                "action_type": "ROUTE_TO_REVIEW",
                "parameters": {"review_queue": "procurement", "reason": "Eval variance"},
                "action_order": 0,
                "rationale": "Human review is appropriate.",
                "requires_approval": True,
            }
        ],
        "limitations": "No payment authority.",
    }
    data.update(overrides)
    return data


def build_fake_output(case: ResolutionEvalCase) -> Any:
    """Return structured output, raw invalid dict, or raise provider error."""
    mode = case.planner_mode

    if mode is PlannerSimMode.PROVIDER_ERROR:
        raise LLMProviderError("Simulated Gemini timeout", code="TIMEOUT")

    if mode is PlannerSimMode.NO_ACTION:
        return ResolutionPlannerGeminiOutput.model_validate(
            {
                "status": "NO_ACTION_RECOMMENDED",
                "reasoning_summary": "No further workflow action is warranted.",
                "proposed_actions": [],
                "limitations": "Informational only.",
            }
        )

    if mode is PlannerSimMode.UNKNOWN_ACTION:
        # Invalid for wire schema Literal — caught as schema failure.
        return {
            "status": "ACTIONS_PROPOSED",
            "reasoning_summary": "Attempt unknown action",
            "proposed_actions": [
                {
                    "action_type": "DELETE_INVOICE",
                    "parameters": {},
                    "action_order": 0,
                    "rationale": "bad",
                    "requires_approval": True,
                }
            ],
            "limitations": "",
        }

    if mode is PlannerSimMode.FORBIDDEN_ACTION:
        return {
            "status": "ACTIONS_PROPOSED",
            "reasoning_summary": "Attempt financial mutation",
            "proposed_actions": [
                {
                    "action_type": "MODIFY_INVOICE",
                    "parameters": {"amount": "1.00"},
                    "action_order": 0,
                    "rationale": "mutate",
                    "requires_approval": True,
                }
            ],
            "limitations": "",
        }

    if mode is PlannerSimMode.EXTRA_FIELDS:
        return {
            "status": "ACTIONS_PROPOSED",
            "reasoning_summary": "Extra field injection",
            "proposed_actions": [
                {
                    "action_type": "ROUTE_TO_REVIEW",
                    "parameters": {"review_queue": "procurement"},
                    "action_order": 0,
                    "rationale": "ok",
                    "requires_approval": True,
                    "execute_now": True,
                }
            ],
            "limitations": "",
        }

    if mode is PlannerSimMode.MALFORMED_PARAMS:
        # Valid action type, invalid parameters for typed contract.
        return ResolutionPlannerGeminiOutput.model_validate(
            {
                "status": "ACTIONS_PROPOSED",
                "reasoning_summary": "Bad parameters",
                "proposed_actions": [
                    {
                        "action_type": "ROUTE_TO_REVIEW",
                        "parameters": {"review_queue": ""},  # empty → contract fail
                        "action_order": 0,
                        "rationale": "bad params",
                        "requires_approval": True,
                    }
                ],
                "limitations": "",
            }
        )

    if mode is PlannerSimMode.INJECTION_SAFE:
        # Ignore adversarial untrusted text; propose safe review only.
        return ResolutionPlannerGeminiOutput.model_validate(_valid_route())

    # VALID — pick first allowed action when present.
    action = (
        sorted(case.allowed_actions)[0] if case.allowed_actions else "ROUTE_TO_REVIEW"
    )

    if action == "REQUEST_VENDOR_CLARIFICATION":
        params: dict[str, Any] = {
            "question": "Please clarify the charge difference.",
            "vendor_reference": "VENDOR-EVAL-1",
        }
    elif action == "REQUEST_MISSING_DOCUMENT":
        params = {
            "document_type": "PACKING_SLIP",
            "reason": "Supporting document not attached",
        }
    elif action == "ESCALATE_TO_MANAGER":
        params = {"reason": "Material variance needs manager review", "destination": "AP_MANAGER"}
    else:
        params = {"review_queue": "procurement", "reason": "Eval review"}

    return ResolutionPlannerGeminiOutput.model_validate(
        _valid_route(
            proposed_actions=[
                {
                    "action_type": action,
                    "parameters": params,
                    "action_order": 0,
                    "rationale": f"Deterministic eval proposal for {case.case_id}",
                    "requires_approval": True,
                }
            ]
        )
    )


class FakeResolutionPlannerLLM:
    """Case-bound deterministic LLM provider for offline M8 evaluation."""

    def __init__(self) -> None:
        self.current_case: ResolutionEvalCase | None = None
        self.calls: list[str] = []
        self.model = "fake-resolution-planner-eval"

    def bind(self, case: ResolutionEvalCase) -> None:
        self.current_case = case

    def generate_structured(self, *, system_instruction, user_content, response_model):
        if self.current_case is None:
            raise RuntimeError("FakeResolutionPlannerLLM has no bound case")
        self.calls.append(self.current_case.case_id)
        raw = build_fake_output(self.current_case)
        if isinstance(raw, Exception):
            raise raw
        parsed = raw if isinstance(raw, response_model) else response_model.model_validate(raw)
        return StructuredLLMResponse(
            output=parsed,
            raw_text=parsed.model_dump_json()
            if hasattr(parsed, "model_dump_json")
            else str(parsed),
            model=self.model,
            provider="fake",
            usage=LLMUsageMetadata(input_tokens=8, output_tokens=16, total_tokens=24),
        )

    def extract_structured(self, **kwargs):  # noqa: ANN003
        raise NotImplementedError
