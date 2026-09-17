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

The LLM / AI layer must **not** determine ground truth. AI will assist later with explanation, policy retrieval (RAG), prioritization, and resolution suggestions. Humans remain in the approval loop.

## Current scope

Completed milestones:

- **M0** — FastAPI foundation, domain enums/Pydantic models, health endpoint, tooling
- **M1** — SQLAlchemy persistence layer, Alembic migrations, relational procurement schema
- **M2** — Deterministic PO ↔ GRN ↔ Invoice reconciliation engine, service, and API

Not yet implemented: OCR, LLM/RAG/agents, auth, frontend, cloud deployment.

## Current architecture

```
reconai/
├── app/
│   ├── main.py
│   ├── core/config.py
│   ├── api/routes/          # Thin HTTP adapters
│   ├── domain/              # Enums + Pydantic DTOs
│   ├── db/                  # SQLAlchemy ORM
│   ├── reconciliation/      # Pure deterministic engine (no FastAPI)
│   ├── schemas/             # API DTOs
│   ├── services/            # Load data → engine → persist
│   └── repositories/
├── alembic/
├── tests/
└── docker-compose.yml
```

| Layer | Responsibility |
| --- | --- |
| `reconciliation/` | Pure rules + engine; FastAPI-independent |
| `services/` | Load ORM data, invoke engine, upsert exceptions |
| `api/` | HTTP validation and response mapping only |
| `db/` | Persistence models and sessions |

### Reconciliation (M2)

`POST /reconciliation/run` accepts PO and/or invoice IDs, runs deterministic matching, and persists exceptions idempotently via a unique `fingerprint`.

Rules covered: quantity (multi-GRN aggregation, partial delivery safe), price, tax rate, identifiers, missing documents, duplicate invoice identity, impossible chronology.

## Intentionally not implemented yet

- OCR / document ingestion pipelines
- LLM, RAG, or agent functionality
- Authentication / authorization
- Frontend
- Payments
- Cloud deployment

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

```bash
docker compose up -d
alembic upgrade head
```

`DATABASE_URL` default: `postgresql+psycopg://reconai:reconai@localhost:5432/reconai`

```bash
uvicorn app.main:app --reload
```

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Tests

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
```
