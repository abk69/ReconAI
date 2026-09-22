# M9 — Procurement Anomaly & Risk Intelligence

## Purpose

M9 identifies **unusual procurement patterns** and emits explainable
**anomaly signals**. It does not determine fraud, replace M2 reconciliation,
modify financial truth, execute workflow actions, or call an LLM.

> **M9.1 produces explainable risk signals, not fraud determinations.**

## Anomaly vs fraud

| Anomaly signal (good) | Fraud accusation (forbidden) |
| --- | --- |
| Invoice value is 2.7× vendor's recent baseline | This vendor is committing fraud |
| Invoice date precedes purchase order date | Supplier is fabricating documents |

Signals are risk indicators for human review — never legal or compliance verdicts.

## M9.1 scope — Anomaly Detection Foundation

Deterministic, explainable, testable rules only.

| Included | Not included |
| --- | --- |
| Six explicit anomaly types | Arbitrary / generic anomaly types |
| Config-driven severity thresholds | LLM-chosen severity |
| Structured evidence + fingerprints | Free-form-only explanations |
| Idempotent persistence | Batch / scheduled scanning (M9.2) |
| Detect by invoice / vendor / exception | Unrestricted `detect_everything` |
| Read-only vs financial tables | Financial mutations / Gemini |

## Architecture

```
Authoritative M2 documents / exceptions
        │
        ▼
  AnomalyEngine (explicit rules)
        │
        ▼
  AnomalySignal (typed + evidence + fingerprint)
        │
        ▼
  anomaly_signals (upsert by fingerprint)
```

Package layout:

```
app/anomaly/
  enums.py          AnomalyType, AnomalySeverity
  contracts.py      AnomalySignal, AnomalyConfig
  fingerprints.py   SHA-256 identity fingerprints
  evidence.py       Structured evidence + deterministic explanations
  rules.py          One class per anomaly type
  engine.py         AnomalyEngine orchestration
app/services/anomaly_service.py
app/api/routes/anomalies.py
```

## Anomaly types

| Type | Meaning |
| --- | --- |
| `PRICE_VARIANCE` | Invoice unit price vs linked PO unit price |
| `QUANTITY_VARIANCE` | Invoice quantity vs linked PO quantity |
| `DUPLICATE_INVOICE` | Same vendor + normalized invoice number, multiple rows |
| `TIMING_ANOMALY` | Unusual PO / GRN / Invoice date ordering or delay |
| `VENDOR_SPIKE` | Invoice total vs simple historical average |
| `REPEATED_MISMATCH` | Elevated reconciliation-exception rate for a vendor |

## Severity

`LOW` · `MEDIUM` · `HIGH` · `CRITICAL`

Severity is **deterministic** from thresholds. An LLM never chooses it.

### Score

`score` is a **normalized severity score** in `[0, 1]`:

| Severity | Score |
| --- | --- |
| LOW | 0.25 |
| MEDIUM | 0.50 |
| HIGH | 0.75 |
| CRITICAL | 1.00 |

It is **not** a probability of fraud.

## Thresholds (defaults)

Configuration via environment / `Settings` (Decimal-safe strings where monetary/%).

### Price variance (`ANOMALY_PRICE_*_PCT`)

| Severity | Threshold |
| --- | --- |
| LOW | ≥ 5% |
| MEDIUM | ≥ 10% |
| HIGH | ≥ 25% |
| CRITICAL | ≥ 50% |

Below LOW → no signal.

### Quantity variance (`ANOMALY_QUANTITY_*_PCT`)

Same ladder as price (defaults 5 / 10 / 25 / 50). Below LOW → no signal.
Zero expected quantity with nonzero invoice → treated as 100% variance.

### Vendor spike

| Setting | Default |
| --- | --- |
| `VENDOR_SPIKE_MIN_HISTORY` | 3 prior invoices |
| `VENDOR_SPIKE_MEDIUM_RATIO` | 2.0 |
| `VENDOR_SPIKE_HIGH_RATIO` | 3.0 |
| `VENDOR_SPIKE_CRITICAL_RATIO` | 5.0 |

Baseline = average of prior invoices (excluding current). Insufficient history → no signal.

### Repeated mismatch

| Setting | Default |
| --- | --- |
| `REPEATED_MISMATCH_MIN_HISTORY` | 5 invoices in window |
| `REPEATED_MISMATCH_MEDIUM_RATE` | 0.30 |
| `REPEATED_MISMATCH_HIGH_RATE` | 0.50 |
| `REPEATED_MISMATCH_CRITICAL_RATE` | 0.75 |
| window days | 90 |

Uses authoritative `reconciliation_exceptions` linked to vendor invoices.

### Timing

| Rule | Severity |
| --- | --- |
| Invoice date before PO date | HIGH |
| Invoice date before GRN date | MEDIUM |
| PO→invoice delay > `TIMING_LONG_DELAY_DAYS` (default 30) | LOW |

## Evidence

Every signal stores **structured evidence** (JSON) plus a deterministic explanation
derived from those facts — never Gemini prose.

Example `PRICE_VARIANCE`:

```json
{
  "po_unit_price": "100.00",
  "invoice_unit_price": "150.00",
  "variance_amount": "50.00",
  "variance_percent": "50.00",
  "purchase_order_line_id": "...",
  "invoice_line_id": "..."
}
```

## Fingerprints & idempotency

SHA-256 over stable identity parts only (type, entity IDs, rule key). Excludes
timestamps, random UUIDs, scores, and explanation text.

`anomaly_signals.fingerprint` is **unique**. Re-running detection returns the
existing row — no duplicate inserts.

## API

```bash
POST /anomalies/detect/invoice/{invoice_id}
POST /anomalies/detect/vendor/{vendor_id}
POST /anomalies/detect/exception/{exception_id}
GET  /anomalies/{anomaly_id}
GET  /anomalies?anomaly_type=&severity=&vendor_id=&invoice_id=&purchase_order_id=&detected_from=&detected_to=
```

Detection does not mutate PO / Invoice / GRN financial columns.

## Limitations

- Simple baselines (averages / rates) — no ML.
- Duplicate detection depends on normalized invoice numbers across rows.
- Vendor spike ignores currency FX and seasonality.
- Repeated mismatch fingerprint is day-scoped for the lookback window end date.
- No scheduled bulk scan yet (M9.2).
- Signals are not automatically linked to M8 resolution plans.

## Later (post M9.1)

- Batch / scheduled detection
- Richer baselines and cohort comparisons
- Optional LLM narrative *after* deterministic facts (still not fraud verdicts)
- UI triage queues for high/critical signals
