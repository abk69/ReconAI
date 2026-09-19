# M6 behavior guide (interview / developer reference)

This document explains what ReconAI does in each M6 situation.
Gemini is a **probabilistic assistant**. Deterministic guardrails (M4/M5/M2) remain authoritative.

## Pipeline

```
Document → M4 deterministic extraction
         → Quality gate (cost control)
              ├─ M4 READY → skip Gemini; keep M4 result
              └─ needs help → Gemini structured extraction
                   → Pydantic schema validation
                   → Evidence grounding
                   → Business validation (M4 validator)
                   → M4 vs Gemini comparison
                   → Application quality (HIGH/MEDIUM/REVIEW_REQUIRED)
                   → Persist LlmExtractionResult (does NOT overwrite M4)
                   → M5 ReviewTask (human trust boundary)
                   → PromotionService → PO/GRN/Invoice
                   → M2 reconciliation
```

## What happens when…

### 1. M4 succeeds (`READY_FOR_RECONCILIATION`)?
Quality gate **skips Gemini**. No API call. `invocation_status=SKIPPED_M4_SUFFICIENT`.
M4 candidate remains the only extraction. Cost controlled.

### 2. M4 is ambiguous (`REVIEW_REQUIRED` / UNKNOWN / OCR missing)?
Gate **invokes Gemini** with untrusted document text + tables from M4 raw extraction.
Result is validated, grounded, compared, and a review task is ensured.

### 3. Gemini fails (network, 500, auth)?
`invocation_status=PROVIDER_ERROR`. Document stays/`REVIEW_REQUIRED`.
Review task created/updated with safe error code (no secrets). M4 still usable.

### 4. Gemini produces invalid JSON / schema mismatch?
Provider raises `SCHEMA_INVALID` / `MALFORMED_RESPONSE`.
Treated as provider error → `REVIEW_REQUIRED`. No infinite retries on bad schema.

### 5. Gemini produces valid JSON with wrong financial values?
Evidence check and/or M4 comparison catches unsupported or disagreed values →
`REVIEW_REQUIRED` / `DISAGREEMENT`. Values are **not** auto-selected over M4.
Human must approve/correct via M5 before promotion.

### 6. Gemini disagrees with M4 on quantity/price/identifiers?
`ComparisonResult.has_financial_disagreement=true`.
Both values preserved in comparison JSON. Review task priority HIGH.
Gemini is **not** automatically preferred.

### 7. Evidence cannot be found in the document?
`EVIDENCE_FAILED` / application quality `REVIEW_REQUIRED`.
Unsupported field list stored. Candidate cannot become authoritative.

### 8. Document contains prompt injection?
System prompt declares document text UNTRUSTED.
Injection text is treated as content. Even if the model obeys it, schema +
evidence + business validation + M5 + promotion boundary block financial writes.

### 9. Gemini API quota exceeded (429)?
Mapped to `RATE_LIMIT`. Bounded retry (default 1). Then `PROVIDER_ERROR` /
`REVIEW_REQUIRED`. No retry storm.

### 10. Reviewer corrects a Gemini-assisted result?
M5 corrections update `reviewed_candidate` + `ReviewDecision` audit.
M4 and LLM extraction rows remain intact.
Only `PromotionService` after APPROVED/CORRECTED writes PO/GRN/Invoice.

## Invariants

| Layer | Role |
| --- | --- |
| M4 | Deterministic baseline extraction |
| M6 | Gemini-assisted **candidate** generation |
| M5 | Human trust / review / audit |
| M2 | Financial reconciliation truth |

**Gemini never bypasses these boundaries.**
