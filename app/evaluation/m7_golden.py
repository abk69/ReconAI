"""M7.5 golden policy RAG evaluation dataset (deterministic, no LLM judge)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

DATASET_ID = "m7_policy_eval_v1"


class EvalCategory(StrEnum):
    RELEVANT_POLICY = "RELEVANT_POLICY"
    NO_RELEVANT_POLICY = "NO_RELEVANT_POLICY"
    VERSIONED_POLICY = "VERSIONED_POLICY"
    CONFLICTING_POLICY = "CONFLICTING_POLICY"
    CITATION_GROUNDING = "CITATION_GROUNDING"
    BOUNDARY_CASE = "BOUNDARY_CASE"


@dataclass(frozen=True)
class GoldenPolicySource:
    """Synthetic policy markdown used to seed the eval corpus."""

    key: str
    name: str
    version_label: str
    markdown: str
    status: str = "ACTIVE"  # PolicyVersionStatus value


@dataclass(frozen=True)
class EvaluationCase:
    """One golden evaluation case with expected retrieval/grounding outcomes."""

    id: str
    category: EvalCategory
    query: str
    # Which seeded policy version to scope retrieval to (None = all versions).
    policy_key: str | None
    # Section ids that should be retrieved (empty => no relevant evidence expected).
    expected_section_ids: tuple[str, ...] = ()
    # Optional content substrings that must appear in expected chunks.
    expected_content_markers: tuple[str, ...] = ()
    expected_status: str | None = None
    expected_answer_facts: dict[str, str] = field(default_factory=dict)
    # Grounding simulation mode for offline eval (not used for pure retrieval cases).
    grounding_mode: str | None = None
    # Special: force dual-version conflict scenario in grounding eval.
    force_conflict: bool = False
    top_k: int = 3
    notes: str = ""


# --- Synthetic policies -------------------------------------------------------

PRICE_V1 = GoldenPolicySource(
    key="price_v2026_1",
    name="Price Variance Policy",
    version_label="2026.1",
    markdown="""# Price Variance Policy

## 1. Purpose

This policy defines acceptable unit-price variance between purchase orders and invoices.

## 2. Rules

Price variance must not exceed two percent of the purchase order unit price without
written approval from Procurement. The allowed_variance_percent is 2.
Variances above two percent require_review_above_percent of 2.
""",
)

PRICE_V2 = GoldenPolicySource(
    key="price_v2026_2",
    name="Price Variance Policy",
    version_label="2026.2",
    markdown="""# Price Variance Policy

## 1. Purpose

This policy defines acceptable unit-price variance between purchase orders and invoices.

## 2. Rules

Price variance must not exceed three percent of the purchase order unit price without
written approval from Procurement. The allowed_variance_percent is 3.
Variances above three percent require_review_above_percent of 3.
""",
)

QTY_POLICY = GoldenPolicySource(
    key="quantity_v1",
    name="Quantity Tolerance Policy",
    version_label="2026.1",
    markdown="""# Quantity Tolerance Policy

## 1. Purpose

Controls over-delivery on goods receipts relative to purchase orders.

## 2. Rules

Quantity over-delivery must not exceed five percent of the ordered quantity.
The allowed_over_delivery_percent is 5.
""",
)

TAX_POLICY = GoldenPolicySource(
    key="tax_v1",
    name="Tax Rate Policy",
    version_label="2026.1",
    markdown="""# Tax Rate Policy

## 1. Purpose

Tax rate discrepancies between PO and invoice.

## 2. Rules

Tax rate differences above one percent require human review before promotion.
The tax_rate_tolerance_percent is 1.
""",
)

GOLDEN_POLICIES: list[GoldenPolicySource] = [
    PRICE_V1,
    PRICE_V2,
    QTY_POLICY,
    TAX_POLICY,
]


# --- Cases --------------------------------------------------------------------

EVAL_CASES: list[EvaluationCase] = [
    EvaluationCase(
        id="ret-price-relevant",
        category=EvalCategory.RELEVANT_POLICY,
        query="unit price variance tolerance purchase order invoice percent",
        policy_key="price_v2026_1",
        expected_section_ids=("2",),
        expected_content_markers=("two percent",),
        expected_status="SUPPORTED",
        expected_answer_facts={
            "allowed_variance_percent": "2",
            "requires_review_above_percent": "2",
        },
        grounding_mode="supported_cite_relevant",
        notes="Core price policy retrieval + grounded facts",
    ),
    EvaluationCase(
        id="ret-qty-relevant",
        category=EvalCategory.RELEVANT_POLICY,
        query="quantity over-delivery tolerance goods receipt ordered quantity",
        policy_key="quantity_v1",
        expected_section_ids=("2",),
        expected_content_markers=("five percent",),
        expected_status="SUPPORTED",
        expected_answer_facts={"allowed_over_delivery_percent": "5"},
        grounding_mode="supported_cite_relevant",
    ),
    EvaluationCase(
        id="ret-tax-relevant",
        category=EvalCategory.RELEVANT_POLICY,
        query="tax rate discrepancy invoice purchase order tolerance review",
        policy_key="tax_v1",
        expected_section_ids=("2",),
        expected_content_markers=("one percent",),
        expected_status="SUPPORTED",
        expected_answer_facts={"tax_rate_tolerance_percent": "1"},
        grounding_mode="supported_cite_relevant",
    ),
    EvaluationCase(
        id="ret-no-relevant",
        category=EvalCategory.NO_RELEVANT_POLICY,
        query="employee vacation leave accrual remote work laptop stipend",
        policy_key="price_v2026_1",
        expected_section_ids=(),
        expected_status="INSUFFICIENT_EVIDENCE",
        grounding_mode="insufficient_no_call",
        notes="Unrelated HR query against procurement policy",
    ),
    EvaluationCase(
        id="ret-version-2pct",
        category=EvalCategory.VERSIONED_POLICY,
        query="price variance allowed percent procurement approval",
        policy_key="price_v2026_1",
        expected_section_ids=("2",),
        expected_content_markers=("two percent",),
        expected_status="SUPPORTED",
        expected_answer_facts={"allowed_variance_percent": "2"},
        grounding_mode="supported_cite_relevant",
        notes="Must retrieve 2026.1 (2%), not 2026.2 (3%)",
    ),
    EvaluationCase(
        id="ret-version-3pct",
        category=EvalCategory.VERSIONED_POLICY,
        query="price variance allowed percent procurement approval",
        policy_key="price_v2026_2",
        expected_section_ids=("2",),
        expected_content_markers=("three percent",),
        expected_status="SUPPORTED",
        expected_answer_facts={"allowed_variance_percent": "3"},
        grounding_mode="supported_cite_relevant",
        notes="Must retrieve 2026.2 (3%), not 2026.1 (2%)",
    ),
    EvaluationCase(
        id="gnd-conflict-active",
        category=EvalCategory.CONFLICTING_POLICY,
        query="price variance tolerance percent",
        policy_key=None,
        expected_section_ids=("2",),
        expected_content_markers=("percent",),
        expected_status="CONFLICTING_POLICY",
        force_conflict=True,
        grounding_mode="conflict",
        notes="Two ACTIVE price versions must surface CONFLICTING_POLICY",
    ),
    EvaluationCase(
        id="gnd-citation-ok",
        category=EvalCategory.CITATION_GROUNDING,
        query="unit price variance two percent policy",
        policy_key="price_v2026_1",
        expected_section_ids=("2",),
        expected_content_markers=("two percent",),
        expected_status="SUPPORTED",
        expected_answer_facts={"allowed_variance_percent": "2"},
        grounding_mode="supported_cite_relevant",
    ),
    EvaluationCase(
        id="gnd-citation-fabricated",
        category=EvalCategory.CITATION_GROUNDING,
        query="unit price variance two percent policy",
        policy_key="price_v2026_1",
        expected_section_ids=("2",),
        expected_content_markers=("two percent",),
        expected_status="INSUFFICIENT_EVIDENCE",
        grounding_mode="fabricated_citation",
        notes="Fabricated citation IDs must be rejected",
    ),
    EvaluationCase(
        id="gnd-zero-citation-supported",
        category=EvalCategory.CITATION_GROUNDING,
        query="unit price variance two percent policy",
        policy_key="price_v2026_1",
        expected_section_ids=("2",),
        expected_content_markers=("two percent",),
        expected_status="INSUFFICIENT_EVIDENCE",
        grounding_mode="zero_citation_supported",
        notes="SUPPORTED with zero citations must be downgraded",
    ),
    EvaluationCase(
        id="gnd-weak-threshold",
        category=EvalCategory.BOUNDARY_CASE,
        query="unit price variance purchase order",
        policy_key="price_v2026_1",
        expected_section_ids=(),
        expected_status="INSUFFICIENT_EVIDENCE",
        grounding_mode="insufficient_high_threshold",
        notes="Similarity threshold blocks all hits → abstain",
    ),
    EvaluationCase(
        id="gnd-empty-kb",
        category=EvalCategory.NO_RELEVANT_POLICY,
        query="price variance tolerance",
        policy_key=None,
        expected_section_ids=(),
        expected_status="INSUFFICIENT_EVIDENCE",
        grounding_mode="insufficient_empty_kb",
        notes="No embedded chunks available",
    ),
]


def get_case(case_id: str) -> EvaluationCase:
    for case in EVAL_CASES:
        if case.id == case_id:
            return case
    raise KeyError(f"Unknown evaluation case: {case_id}")


def cases_by_category(category: EvalCategory) -> list[EvaluationCase]:
    return [c for c in EVAL_CASES if c.category == category]


def dataset_summary() -> dict[str, Any]:
    return {
        "dataset": DATASET_ID,
        "policy_sources": len(GOLDEN_POLICIES),
        "cases": len(EVAL_CASES),
        "categories": sorted({c.category.value for c in EVAL_CASES}),
    }
