# ReconAI

Intelligent procurement reconciliation and exception-resolution platform.

## The problem

Businesses routinely receive related procurement documents:

- **Purchase Orders (PO)** — what was ordered
- **Goods Receipts / GRNs** — what was received
- **Vendor Invoices** — what the supplier billed

These documents often disagree on quantities, prices, taxes, identifiers, dates, and related fields. Teams also face duplicate invoices, partial deliveries, and missing documents. Manual three-way matching is slow, error-prone, and hard to audit.

ReconAI aims to ingest these documents, reconcile them deterministically, surface exceptions with evidence, and later assist humans with policy-aware explanations and resolution workflows.

## Architectural principle

**The deterministic reconciliation engine establishes financial facts.**

The LLM / AI layer must **not** determine ground truth. AI will assist with:

- Explaining exceptions
- Retrieving relevant company policies (RAG)
- Prioritizing work
- Suggesting resolution actions

Humans remain in the approval loop. Every decision and action will be auditable.

## Current scope

Completed milestones:

- **M0** — FastAPI foundation, domain enums/Pydantic models, health endpoint, tooling
- **M1** — SQLAlchemy persistence layer, Alembic migrations, relational procurement schema

Not yet implemented: reconciliation engine, OCR, LLM/RAG/agents, auth, frontend, cloud deployment.

## Current architecture

```
reconai/
├── app/
│   ├── main.py              # FastAPI app factory and entrypoint
│   ├── core/config.py       # Settings from environment variables
│   ├── api/routes/          # Thin HTTP adapters (no business logic)
│   ├── domain/              # Enums and Pydantic domain models
│   ├── db/                  # SQLAlchemy Base, session, ORM models
│   ├── schemas/             # API response schemas
│   ├── services/            # Business logic (future)
│   └── repositories/        # Persistence helpers (future)
├── alembic/                 # Database migrations
├── tests/
├── docker-compose.yml       # Local PostgreSQL
├── alembic.ini
├── pyproject.toml
└── requirements.txt
```

| Layer | Responsibility |
| --- | --- |
| `api/` | HTTP routing and response shapes only |
| `domain/` | Shared enums and Pydantic models |
| `db/` | SQLAlchemy ORM models, engine, sessions |
| `schemas/` | API DTOs |
| `services/` | Reserved for reconciliation and workflows |
| `repositories/` | Reserved for query/command helpers |

### Database architecture (M1)

PostgreSQL is the target database. ORM models live in `app/db/models.py`:

| Table | Role |
| --- | --- |
| `vendors` | Supplier master data (indexed `tax_id`) |
| `purchase_orders` / `purchase_order_lines` | Ordered quantities and prices |
| `goods_receipts` / `goods_receipt_lines` | Received quantities linked to PO lines |
| `invoices` / `invoice_lines` | Billed amounts linked to vendor / optional PO |
| `reconciliation_exceptions` | Detected exceptions with FK source docs + JSON evidence |

Design notes:

- UUID primary keys
- `Numeric` for all monetary and quantity columns (never float)
- Timezone-aware timestamps
- Unique business identifiers: `po_number`, `grn_number`, `invoice_number`, `vendors.tax_id`
- Exception `evidence` and `source_document_ids` stored as JSONB on PostgreSQL (JSON variant for isolated SQLite tests)

Pydantic models in `app/domain/models.py` remain API/domain DTOs; ORM models are the persistence source of truth for M1+.

## Intentionally not implemented yet

- Deterministic reconciliation engine
- OCR / document ingestion pipelines
- LLM, RAG, or agent functionality
- Authentication / authorization
- Frontend
- Payments
- Cloud deployment
- Repository service layer wiring into API routes

## Local setup

Requires **Python 3.11+**.

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### Local PostgreSQL

Production and local app runtime use PostgreSQL. The included Compose file matches `.env.example`:

```bash
docker compose up -d
alembic upgrade head
```

`DATABASE_URL` default:

`postgresql+psycopg://reconai:reconai@localhost:5432/reconai`

Override via environment or `.env`. Do not hardcode production credentials.

Run the API:

```bash
uvicorn app.main:app --reload
```

Then open [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) or docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Tests

ORM and Alembic tests use an **isolated SQLite database** so they never require your developer/production PostgreSQL. Production schema behavior remains PostgreSQL-first (JSONB via dialect variants).

```bash
pytest
```

## Lint

```bash
ruff check .
ruff format --check .
```

## Migrations

```bash
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "describe change"
```
