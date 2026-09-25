"""Latency summaries and estimated-cost math for M11.5.

Durations use a monotonic clock. Token totals are provider-reported only.
Prices are never assumed.
"""

from __future__ import annotations

import math
from decimal import Decimal
from time import perf_counter
from typing import Any

PRICING_VERSION = "m11.5-unpriced"
TOKEN_USAGE_UNAVAILABLE = "TOKEN_USAGE_UNAVAILABLE"
COST_UNAVAILABLE = "COST_UNAVAILABLE"


def monotonic_ms() -> float:
    """Milliseconds from time.perf_counter, not wall-clock time."""
    return perf_counter() * 1000.0


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. For n=5, p95 is the largest sample."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if pct <= 0 or pct > 100:
        raise ValueError("pct must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(pct / 100.0 * len(ordered))
    return ordered[rank - 1]


def summarize(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "median": round(median, 3),
        "p95": round(percentile(ordered, 95), 3),
        "max": round(ordered[-1], 3),
        "p95_method": "nearest-rank",
    }


def usage_report(
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
) -> dict[str, Any]:
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return {"status": TOKEN_USAGE_UNAVAILABLE}
    counts = (input_tokens, output_tokens, total_tokens)
    if any(value is not None and value < 0 for value in counts):
        raise ValueError("token counts must not be negative")
    return {
        "status": "PROVIDER_REPORTED",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def estimate_cost(
    input_tokens: int | None,
    output_tokens: int | None,
    *,
    input_price_per_million: Decimal | None,
    output_price_per_million: Decimal | None,
    pricing_version: str,
) -> dict[str, Any]:
    """Estimate cost from an explicit price fixture. This is not a billing charge."""
    if input_price_per_million is None or output_price_per_million is None:
        return {"status": COST_UNAVAILABLE, "pricing_version": pricing_version}
    if input_tokens is None or output_tokens is None:
        return {"status": COST_UNAVAILABLE, "pricing_version": pricing_version}
    input_cost = Decimal(input_tokens) / Decimal(1_000_000) * input_price_per_million
    output_cost = Decimal(output_tokens) / Decimal(1_000_000) * output_price_per_million
    return {
        "status": "ESTIMATED",
        "pricing_version": pricing_version,
        "estimated_input_cost": str(input_cost),
        "estimated_output_cost": str(output_cost),
        "estimated_total_cost": str(input_cost + output_cost),
        "note": "Estimate from a local price fixture. Not an actual billing charge.",
    }
