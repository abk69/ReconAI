"""LLM provider abstraction — application depends on this, not Google SDK details."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.llm.schemas import GeminiExtractionOutput


@dataclass(frozen=True)
class LLMUsageMetadata:
    """Token usage as reported by the provider (never invented)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class LLMResponse:
    """Structured provider response after a successful Gemini call."""

    output: GeminiExtractionOutput
    raw_text: str | None
    model: str
    provider: str
    usage: LLMUsageMetadata = field(default_factory=LLMUsageMetadata)
    provider_metadata: dict[str, Any] = field(default_factory=dict)


class LLMProviderError(Exception):
    """Provider-level failure (auth, timeout, rate limit, malformed response)."""

    def __init__(self, message: str, *, code: str = "PROVIDER_ERROR") -> None:
        super().__init__(message)
        self.code = code


class LLMProvider(ABC):
    """Interface for a real LLM extraction provider."""

    @abstractmethod
    def extract_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
    ) -> LLMResponse:
        """Call the provider and return validated structured output."""
