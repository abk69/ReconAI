"""LLM provider abstraction — application depends on this, not Google SDK details."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.llm.schemas import GeminiExtractionOutput

TModel = TypeVar("TModel", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsageMetadata:
    """Token usage as reported by the provider (never invented)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class StructuredLLMResponse:
    """Validated structured provider response for an arbitrary Pydantic schema."""

    output: BaseModel
    raw_text: str | None
    model: str
    provider: str
    usage: LLMUsageMetadata = field(default_factory=LLMUsageMetadata)
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Structured provider response after a successful Gemini extraction call."""

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
    """Interface for a real LLM provider (extraction + grounded generation)."""

    @abstractmethod
    def extract_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
    ) -> LLMResponse:
        """Call the provider and return validated M6 extraction output."""

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[TModel],
    ) -> StructuredLLMResponse:
        """Call the provider with an arbitrary Pydantic response schema.

        Default raises — concrete providers (Gemini) override. Keeps M6 callers
        working while M7.4 reuses the same client/retry/schema-compat path.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement generate_structured."
        )
