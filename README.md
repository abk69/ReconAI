# ReconAI

Intelligent procurement reconciliation and exception-resolution platform.

## The problem

Businesses routinely receive related procurement documents (PO, GRN, Invoice) that disagree on quantities, prices, taxes, identifiers, and dates. ReconAI ingests these documents, reconciles them deterministically, and later assists humans with policy-aware resolution.

## Architectural principle

**The deterministic reconciliation engine establishes financial facts.** LLMs must not determine ground truth. AI (RAG/agents) arrives in later milestones.

## Current scope

| Milestone | Status |
| --- | --- |
| M0 Foundation | Done |
| M1 Persistence | Done |
| M2 Deterministic reconciliation | Done |
| M3 Document + structured intake | Done |
| M4 Extraction / OCR / understanding | Not started |

## Architecture

```
API → services → (storage filesystem | PostgreSQL metadata | reconciliation engine)
```

### Document intake (M3)

- **PostgreSQL** stores document metadata only
- **Local filesystem** (`STORAGE_ROOT`) stores binaries
- Upload validates extension + MIME + size, computes SHA-256, deduplicates exact content
- Lifecycle after successful intake: **`VALIDATED`** (extraction states reserved for M4)
- **No OCR, PDF parsing, spreadsheet interpretation, or AI extraction in M3**

Supported types: **PDF, JPEG, PNG, XLSX** (default max **10 MB**).

Duplicate strategy: exact SHA-256 match returns **HTTP 200** with existing metadata and `is_duplicate=true` (idempotent). New uploads return **201**.

### Document lifecycle

`UPLOADED` → `VALIDATED` → `EXTRACTION_PENDING` → `EXTRACTING` → `EXTRACTED` → `NORMALIZED` → `READY_FOR_RECONCILIATION`

Failure states: `VALIDATION_FAILED`, `EXTRACTION_FAILED`

M3 sets **`VALIDATED`** after intake checks pass.

## API examples

```bash
# Vendor + PO (structured intake)
curl -X POST http://127.0.0.1:8000/vendors -H "Content-Type: application/json" \
  -d '{"name":"Acme","tax_id":"GSTIN1"}'

curl -X POST http://127.0.0.1:8000/purchase-orders -H "Content-Type: application/json" \
  -d '{"po_number":"PO-1","vendor_id":"<uuid>","order_date":"2026-09-10","lines":[{"line_number":1,"quantity":"100","unit_price":"500","tax_rate":"0.18"}]}'

# Document upload
curl -X POST http://127.0.0.1:8000/documents \
  -F "file=@./po.pdf;type=application/pdf" \
  -F "document_type=PO" \
  -F "purchase_order_id=<uuid>"

# Reconciliation (unchanged from M2)
curl -X POST http://127.0.0.1:8000/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"purchase_order_id":"<uuid>","invoice_id":"<uuid>"}'
```

Routes: `POST/GET /documents`, `PATCH /documents/{id}`, `POST/GET /vendors`, `POST/GET /purchase-orders`, `POST/GET /goods-receipts`, `POST/GET /invoices`, `POST /reconciliation/run`, `GET /health`.

## Security considerations

- Max upload size enforced
- Extension + MIME allowlists
- UUID-based storage filenames (never user paths)
- Path traversal rejected
- SHA-256 checksums; exact-content dedup
- Original filename kept as metadata only
- No shell execution of uploads

## Local setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
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
