"""Deterministic retrieval and grounding metrics for M7.5.

Definitions
-----------
Hit@K
    1 if at least one expected-relevant chunk appears in the top-K retrieved
    results; else 0. When there are **no** expected-relevant chunks, Hit@K is
    **undefined** (``None``) — abstention is measured separately.

Recall@K
    |expected ∩ retrieved_top_k| / |expected|
    When |expected| == 0, Recall@K is undefined → returns None (not 0).

MRR (Mean Reciprocal Rank)
    1 / rank of the first expected-relevant chunk in the ranked list
    (1-based). 0 if none of the expected chunks appear. When |expected| == 0,
    MRR is undefined → returns None.

Citation precision
    |cited ∩ retrieved| / |cited|  (fabricated cites fail). Undefined if no cites.

Citation recall
    |cited ∩ expected_relevant| / |expected_relevant|
    Undefined when |expected_relevant| == 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RankedIdList:
    """Ordered retrieval result IDs (rank 1 = index 0)."""

    ids: tuple[UUID, ...]

    def top_k(self, k: int) -> tuple[UUID, ...]:
        if k < 1:
            raise ValueError("k must be >= 1")
        return self.ids[:k]


def hit_at_k(
    retrieved: list[UUID] | tuple[UUID, ...],
    expected: set[UUID],
    *,
    k: int,
) -> float | None:
    if not expected:
        return None
    top = list(retrieved)[:k]
    return 1.0 if any(cid in expected for cid in top) else 0.0


def recall_at_k(
    retrieved: list[UUID] | tuple[UUID, ...],
    expected: set[UUID],
    *,
    k: int,
) -> float | None:
    if not expected:
        return None
    top = set(list(retrieved)[:k])
    return len(expected & top) / len(expected)


def mean_reciprocal_rank(
    retrieved: list[UUID] | tuple[UUID, ...],
    expected: set[UUID],
) -> float | None:
    if not expected:
        return None
    for index, cid in enumerate(retrieved, start=1):
        if cid in expected:
            return 1.0 / float(index)
    return 0.0


def citation_precision(
    cited: set[UUID],
    retrieved: set[UUID],
) -> float | None:
    """Fraction of cited IDs that appear in the retrieved evidence set."""
    if not cited:
        return None
    valid = cited & retrieved
    return len(valid) / len(cited)


def citation_recall(
    cited: set[UUID],
    expected_relevant: set[UUID],
) -> float | None:
    if not expected_relevant:
        return None
    return len(cited & expected_relevant) / len(expected_relevant)


def answer_fact_accuracy(
    expected_facts: dict[str, str],
    response_text: str,
) -> float | None:
    """Fraction of expected fact values that appear in the concatenated response text.

    Deterministic substring check (case-insensitive). No LLM judge.
    """
    if not expected_facts:
        return None
    haystack = (response_text or "").casefold()
    hits = 0
    for value in expected_facts.values():
        if str(value).casefold() in haystack:
            hits += 1
    return hits / len(expected_facts)


def mean_defined(values: list[float | None]) -> float | None:
    defined = [v for v in values if v is not None]
    if not defined:
        return None
    return sum(defined) / len(defined)
