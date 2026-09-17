# ReconAI

Intelligent procurement reconciliation and exception-resolution platform.

## Architectural principle

**Deterministic reconciliation (M2) establishes financial facts.**  
**Document understanding (M4) extracts candidates with provenance — it does not invent financial truth.**  
**Human review (M5) is the trust boundary between candidates and authoritative PO/GRN/Invoice data.**  
LLMs / RAG / agents are intentionally deferred.

## Milestones

| Milestone | Status |
| --- | --- |
| M0 Foundation | Done |
| M1 Persistence | Done |
| M2 Deterministic reconciliation | Done |
| M3 Document + structured intake | Done |
| M4 Deterministic document understanding | Done |
| M5 Extraction evaluation + human review | Done |
| M6 LLM-assisted extraction (optional) | Not started |

## M5 — Extraction evaluation + human review

M4 produces **untrusted extraction candidates**. M5 evaluates those candidates, queues human review, records field-level corrections with an audit trail, and only then **promotes** approved/corrected data into authoritative PO/GRN/Invoice tables used by M2.

```
M4 DocumentExtractionResult (candidate)
        │
        ├─ clean → READY_FOR_RECONCILIATION (no review task)
        │
        └─ REVIEW_REQUIRED → ReviewTask (PENDING)
                → IN_REVIEW
                → APPROVED | CORRECTED | REJECTED
                        │
                        ├─ REJECTED → DocumentStatus.REVIEW_REJECTED (never reconcile)
                        │
                        └─ APPROVED / CORRECTED
                                → PromotionService (transactional)
                                → PO / GRN / Invoice (+ lines)
                                → DocumentStatus.READY_FOR_RECONCILIATION
                                → M2 reconciliation (unchanged)
```

### Concepts kept separate

| Concept | Meaning |
| --- | --- |
| Extraction candidate | M4 output — untrusted business data |
| Reviewed candidate | Human-approved or corrected working copy + audit decisions |
| Authoritative financial data | Existing PO/GRN/Invoice tables consumed by M2 |

Validation passing in M4 is **not** the same as becoming authoritative. Promotion is the trust boundary.

### Why human review exists

OCR gaps, unknown document types, ambiguous evidence, and incomplete headers/lines must not invent financial facts. Reviewers approve, correct, or reject with a preserved trail of original vs corrected values.

### Review queue API

```bash
GET  /review/tasks
GET  /review/tasks/{task_id}
POST /review/tasks/{task_id}/approve
POST /review/tasks/{task_id}/correct
POST /review/tasks/{task_id}/reject
POST /review/tasks/{task_id}/promote
```

Filters: `status`, `document_type`, `priority`. Responses never expose filesystem storage paths.

### Field-level correction + audit

Corrections use field paths such as `lines[0].quantity`. The original M4 `DocumentExtractionResult.candidate` is never overwritten. Each decision stores reviewer, timestamp, action, field path, original value, corrected value, and reason.

### Evaluation (separate from review)

`app/evaluation/` compares golden expected structures vs actual M4 candidates (no LLM):

- field accuracy / completeness
- line-item count and field metrics
- normalized Decimal / date / string comparison

Golden fixtures live in `app/evaluation/golden.py` (clean invoice, multi-line invoice, PO, partial GRN, malformed/ambiguous).

Evaluation answers: *How well did extraction perform?*  
Review answers: *Can a human trust/approve this candidate?*

### Promotion boundary

Only `APPROVED` or `CORRECTED` tasks may promote. Promotion:

1. Re-validates required fields  
2. Resolves vendor / PO foreign keys  
3. Creates authoritative header + lines in one DB transaction  
4. Links the source `Document`  
5. Is idempotent on repeat  

Rejected / pending / invalid candidates never promote. M2 is not rewritten.

## M4 — Document understanding

M4 turns a stored file into a **validated structured candidate** with evidence. It does **not** write PO/GRN/Invoice financial rows.

```
Stored Document
    → format extractor (PDF / XLSX / Image OCR)
    → ExtractedDocument (raw text/tables + provenance)
    → deterministic classifier
    → normalizer + structured candidate
    → validator
    → DocumentExtractionResult (JSON evidence)
    → DocumentStatus: READY_FOR_RECONCILIATION | REVIEW_REQUIRED | VALIDATION_FAILED
```

Supported formats: PDF (PyMuPDF), XLSX (openpyxl), JPEG/PNG (optional Tesseract — graceful `REVIEW_REQUIRED` if unavailable).

### Why no LLM yet

Classification and field extraction are rule-based and testable. Ambiguous documents become `REVIEW_REQUIRED` instead of guessed financial facts. M6 can add LLM assistance later without replacing M2.

### API

```bash
POST /documents/{id}/understand
GET  /documents/{id}/understanding
```

Responses never expose filesystem storage paths.

## Local setup

```bash
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

## Tests / lint

```bash
pytest -q
ruff check .
ruff format --check .
```
