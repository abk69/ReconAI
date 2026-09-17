# ReconAI

Intelligent procurement reconciliation and exception-resolution platform.

## Architectural principle

**Deterministic reconciliation (M2) establishes financial facts.**  
**Document understanding (M4) extracts candidates with provenance — it does not invent financial truth.**  
LLMs / RAG / agents are intentionally deferred.

## Milestones

| Milestone | Status |
| --- | --- |
| M0 Foundation | Done |
| M1 Persistence | Done |
| M2 Deterministic reconciliation | Done |
| M3 Document + structured intake | Done |
| M4 Deterministic document understanding | Done |
| M5 Human review / evaluation | Not started |
| M6 LLM-assisted extraction (optional) | Not started |

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
