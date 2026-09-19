"""Real Google Gemini provider using the official google-genai SDK."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMUsageMetadata,
    StructuredLLMResponse,
)
from app.llm.schema_compat import gemini_response_json_schema
from app.llm.schemas import GeminiExtractionOutput

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


class GeminiProvider(LLMProvider):
    """Communicate with Google Gemini for structured JSON output.

    No procurement business rules live here — only provider I/O.
    Used by M6 extraction and M7.4 grounded policy reasoning.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._settings.llm_model

    @property
    def provider_name(self) -> str:
        return "google"

    def _ensure_client(self) -> Any:
        api_key = self._settings.gemini_api_key
        if not api_key:
            raise LLMProviderError(
                "GEMINI_API_KEY is not configured.",
                code="MISSING_API_KEY",
            )
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise LLMProviderError(
                    "google-genai package is not installed.",
                    code="SDK_MISSING",
                ) from exc
            self._client = genai.Client(api_key=api_key)
        return self._client

    def extract_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
    ) -> LLMResponse:
        structured = self.generate_structured(
            system_instruction=system_instruction,
            user_content=user_content,
            response_model=GeminiExtractionOutput,
        )
        output = structured.output
        if not isinstance(output, GeminiExtractionOutput):
            output = GeminiExtractionOutput.model_validate(output)
        return LLMResponse(
            output=output,
            raw_text=structured.raw_text,
            model=structured.model,
            provider=structured.provider,
            usage=structured.usage,
            provider_metadata=structured.provider_metadata,
        )

    def generate_structured(
        self,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[TModel],
    ) -> StructuredLLMResponse:
        client = self._ensure_client()
        max_retries = self._settings.llm_max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return self._call_once(
                    client,
                    system_instruction=system_instruction,
                    user_content=user_content,
                    response_model=response_model,
                )
            except LLMProviderError as exc:
                if exc.code in {"MISSING_API_KEY", "SCHEMA_INVALID", "MALFORMED_RESPONSE"}:
                    raise
                last_error = exc
                if attempt >= max_retries:
                    raise
                time.sleep(min(0.5 * (attempt + 1), 2.0))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                mapped = _map_provider_exception(exc)
                retryable = mapped.code in {"RATE_LIMIT", "TIMEOUT", "UNAVAILABLE"}
                if retryable and attempt < max_retries:
                    time.sleep(min(0.5 * (attempt + 1), 2.0))
                    continue
                raise mapped from exc

        raise LLMProviderError(
            f"Gemini call failed after retries: {last_error}",
            code="PROVIDER_ERROR",
        )

    def _call_once(
        self,
        client: Any,
        *,
        system_instruction: str,
        user_content: str,
        response_model: type[TModel],
    ) -> StructuredLLMResponse:
        from google.genai import types

        # Strip additionalProperties for Gemini wire schema (M6 schema_compat).
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_json_schema=gemini_response_json_schema(response_model),
            max_output_tokens=self._settings.llm_max_output_tokens,
            temperature=0.0,
            http_options=types.HttpOptions(timeout=int(self._settings.llm_timeout_seconds * 1000)),
        )

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user_content,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise _map_provider_exception(exc) from exc

        parsed = getattr(response, "parsed", None)
        raw_text = getattr(response, "text", None)

        if parsed is not None:
            if isinstance(parsed, response_model):
                output: BaseModel = parsed
            else:
                try:
                    output = response_model.model_validate(parsed)
                except Exception as exc:
                    raise LLMProviderError(
                        f"Gemini structured output failed Pydantic validation: {exc}",
                        code="SCHEMA_INVALID",
                    ) from exc
        elif raw_text:
            try:
                payload = json.loads(raw_text)
                output = response_model.model_validate(payload)
            except Exception as exc:
                raise LLMProviderError(
                    f"Gemini returned malformed JSON: {exc}",
                    code="MALFORMED_RESPONSE",
                ) from exc
        else:
            raise LLMProviderError(
                "Gemini returned an empty response.",
                code="MALFORMED_RESPONSE",
            )

        usage = _extract_usage(response)
        logger.info(
            "Gemini structured complete model=%s schema=%s input_tokens=%s output_tokens=%s",
            self.model,
            response_model.__name__,
            usage.input_tokens,
            usage.output_tokens,
        )
        return StructuredLLMResponse(
            output=output,
            raw_text=raw_text,
            model=self.model,
            provider=self.provider_name,
            usage=usage,
            provider_metadata={"finish_reason": _finish_reason(response)},
        )


def _extract_usage(response: Any) -> LLMUsageMetadata:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return LLMUsageMetadata()
    return LLMUsageMetadata(
        input_tokens=getattr(meta, "prompt_token_count", None),
        output_tokens=getattr(meta, "candidates_token_count", None),
        total_tokens=getattr(meta, "total_token_count", None),
    )


def _finish_reason(response: Any) -> str | None:
    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            return str(getattr(candidates[0], "finish_reason", None))
    except Exception:  # noqa: BLE001
        return None
    return None


def _map_provider_exception(exc: Exception) -> LLMProviderError:
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    if (
        "401" in text
        or "403" in text
        or "unauthenticated" in text
        or "permission" in text
        or "api key" in text
        or "access_token" in text
    ):
        return LLMProviderError(f"Gemini authentication failed: {exc}", code="AUTH_ERROR")
    if (
        "429" in text
        or "resource_exhausted" in text
        or "rate limit" in text
        or "rate_limit" in text
        or "quota" in text
    ):
        return LLMProviderError(f"Gemini rate limited: {exc}", code="RATE_LIMIT")
    if "timeout" in text or "deadline" in text or "timed out" in name:
        return LLMProviderError(f"Gemini timed out: {exc}", code="TIMEOUT")
    if "unavailable" in text or "503" in text or "500" in text:
        return LLMProviderError(f"Gemini unavailable: {exc}", code="UNAVAILABLE")
    if "400" in text or "invalid_argument" in text or "additional_properties" in text:
        return LLMProviderError(
            f"Gemini rejected request schema/args: {exc}", code="INVALID_ARGUMENT"
        )
    return LLMProviderError(f"Gemini provider error: {exc}", code="PROVIDER_ERROR")
