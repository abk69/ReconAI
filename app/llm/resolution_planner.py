"""Thin Gemini wrapper for M8.3 resolution planning (propose only)."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider, StructuredLLMResponse
from app.llm.gemini import GeminiProvider
from app.llm.resolution_prompts import SYSTEM_INSTRUCTION
from app.llm.resolution_schemas import ResolutionPlannerGeminiOutput


class ResolutionPlanner:
    """Call Gemini with a strict planner schema. Never executes actions."""

    def __init__(
        self,
        *,
        llm: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm = llm or GeminiProvider(self._settings)

    @property
    def model(self) -> str | None:
        return getattr(self._llm, "model", None)

    def plan(self, *, user_content: str) -> StructuredLLMResponse:
        return self._llm.generate_structured(
            system_instruction=SYSTEM_INSTRUCTION,
            user_content=user_content,
            response_model=ResolutionPlannerGeminiOutput,
        )
