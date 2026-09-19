"""Application-level quality scoring (never trust model self-confidence)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import ApplicationQuality
from app.llm.comparison import ComparisonResult
from app.llm.evidence import EvidenceCheckResult


@dataclass
class ApplicationQualityResult:
    quality: ApplicationQuality
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"quality": self.quality.value, "reasons": self.reasons}


def assess_application_quality(
    *,
    structured_valid: bool,
    business_validation_ok: bool,
    evidence: EvidenceCheckResult,
    comparison: ComparisonResult | None,
    provider_error: str | None = None,
) -> ApplicationQualityResult:
    """Compute HIGH / MEDIUM / REVIEW_REQUIRED from measurable signals."""
    reasons: list[str] = []

    if provider_error:
        return ApplicationQualityResult(
            quality=ApplicationQuality.REVIEW_REQUIRED,
            reasons=[f"Provider error: {provider_error}"],
        )
    if not structured_valid:
        return ApplicationQualityResult(
            quality=ApplicationQuality.REVIEW_REQUIRED,
            reasons=["Structured output failed schema validation."],
        )
    if not evidence.is_grounded:
        reasons.append(
            "Unsupported fields without document evidence: "
            + ", ".join(evidence.unsupported_fields)
        )
        return ApplicationQualityResult(
            quality=ApplicationQuality.REVIEW_REQUIRED,
            reasons=reasons,
        )
    if not business_validation_ok:
        reasons.append("Business validation failed for Gemini candidate.")
        return ApplicationQualityResult(
            quality=ApplicationQuality.REVIEW_REQUIRED,
            reasons=reasons,
        )
    if comparison is not None and comparison.has_financial_disagreement:
        reasons.append("Financially significant disagreement with M4.")
        for diff in comparison.financially_significant_disagreements[:10]:
            reasons.append(
                f"Disagree {diff.field_path}: m4={diff.m4_value!r} gemini={diff.gemini_value!r}"
            )
        return ApplicationQualityResult(
            quality=ApplicationQuality.REVIEW_REQUIRED,
            reasons=reasons,
        )

    # Agreement + grounded + valid → HIGH; soft gaps → MEDIUM.
    if comparison is not None and (comparison.m4_only or comparison.gemini_only):
        reasons.append("Candidates partially overlap; some fields only on one side.")
        return ApplicationQualityResult(quality=ApplicationQuality.MEDIUM, reasons=reasons)

    reasons.append("Structured output valid, evidence grounded, business validation passed.")
    if comparison is not None and comparison.agreements:
        reasons.append(f"Agreed with M4 on {len(comparison.agreements)} field(s).")
    return ApplicationQualityResult(quality=ApplicationQuality.HIGH, reasons=reasons)
