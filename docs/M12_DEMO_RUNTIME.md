# M12.2 Demo runtime

ReconAI v1.0 is a single-operator portfolio and demo system. Authentication is not implemented. This guide starts the same three processes from a clean checkout. It does not make the system ready for shared organizational data.

## Architecture

```text
PostgreSQL + pgvector   (Docker Compose)
        |
FastAPI                 (host, app.main:app)
        |
Next.js                 (host, frontend/)
```

The database container does not run migrations. `alembic upgrade head` is a separate step. Gemini is optional. The frontend never receives `GEMINI_API_KEY`.

## Prerequisites

- Python 3.11+
- Node.js 22
- Docker, for the database only
- A virtual environment with `pip install -r requirements.txt`

## Environment setup

Backend settings live in the repository root. Frontend settings live in `frontend/`. Names match `app/core/config.py` and `frontend/lib/config/env.ts`.

| Variable | Where | Role |
| --- | --- | --- |
| `APP_ENV` | backend | `local`, `demo`, or `production` |
| `DEBUG` | backend | Allowed for `local`. Refused when set true for `demo` or `production` |
| `DATABASE_URL` | backend | SQLAlchemy URL, `postgresql+psycopg://...` |
| `POSTGRES_USER` | Compose | Database role. Must match `DATABASE_URL` |
| `POSTGRES_PASSWORD` | Compose | Database password. Must match `DATABASE_URL` |
| `POSTGRES_DB` | Compose | Database name |
| `GEMINI_API_KEY` | backend | Optional. Empty is valid |
| `CORS_ORIGINS` | backend | Browser origin, default `http://localhost:3000` |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | API origin, default `http://localhost:8000` |

`local` may use the Compose fallback account. `demo` and `production` refuse that account and refuse `DEBUG=true`.

PowerShell, demo profile:

```powershell
Copy-Item .env.demo.example .env
Copy-Item frontend\.env.example frontend\.env.local
```

bash:

```bash
cp .env.demo.example .env
cp frontend/.env.example frontend/.env.local
```

`frontend/.env.local` is optional. The UI already defaults to `http://localhost:8000`.

For day-to-day development with debug enabled, copy `.env.example` instead. That file is `APP_ENV=local`.

## Database startup

PowerShell or bash, from the repository root:

```bash
docker compose up -d
```

Compose starts `pgvector/pgvector:pg16` only. The published port is 5432. The volume name is `reconai_pgdata`.

Set `POSTGRES_PASSWORD` before the first start of a new volume. Postgres keeps the password it was initialized with. Changing `.env` later does not change an existing volume. `docker compose down -v` deletes that data.

## Migration

```bash
alembic upgrade head
```

Windows, when the virtualenv is `.venv`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The current head is `0018_risk_profiles`. The application does not migrate itself on startup.

## Backend startup

Demo profile, after `.env` is the demo example:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

bash:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The entrypoint is `app.main:app`. Binding to `127.0.0.1` keeps the demo on this machine. Gemini is not required for the process to start.

## Frontend startup

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The dashboard calls `NEXT_PUBLIC_API_BASE_URL`.

## Gemini

Leave `GEMINI_API_KEY` empty to use reconciliation, review, documents, anomalies, and the offline evaluation runners. Set it in the backend `.env` only when you want live extraction, grounding, or planning. Do not put the key in `frontend/.env.local` or in a `NEXT_PUBLIC_` variable.

## Health and readiness

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | Process is up. Does not touch the database. `{"status":"ok","service":"reconai"}` |
| `GET /ready` | Database answered `SELECT 1`. `{"status":"ready"}` or HTTP 503 `{"status":"not_ready"}` |
| `GET /dashboard/summary` | Read-only counts. Empty after a fresh migration |

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/dashboard/summary
```

bash:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/dashboard/summary
```

Stop the API and `GET /health` fails. That is the unavailable check. Start it again and both health and readiness should succeed after migrations.

## Demo workflow

There is no seed loader. Data you type into the UI is yours. The repository's scripted cases are synthetic and are not loaded into Postgres by the demo start.

After the dashboard opens:

1. Confirm the summary loads. An empty database says that no documents or exceptions are recorded.
2. Upload a file you created. Allowed types are PDF, JPEG, PNG, and XLSX, up to 10 MB. Upload only stores the file. A duplicate file opens the existing document.
3. Open the document and choose Understand document. That calls deterministic extraction and does not call Gemini. The page shows the stored outcome, detected type, and validation issues.
4. If the outcome needs review, open the review task. If the extraction is clean, choose Request review. Approve or correct it, then promote it. Promotion writes the authoritative purchase order, goods receipt, or invoice.
5. From a promoted purchase order or invoice, choose Run reconciliation. The status and any exceptions come from that response. Open an exception to see its stored evidence. A clean match has status `MATCHED` and no exception row.
6. Read the evaluation evidence in `docs/M11_EVALUATION.md`, or regenerate the offline report:

```bash
python -m app.evaluation.m11_report_runner
```

That runner does not call Gemini and does not fill the demo database.

## Shutdown

Stop the API and `npm run dev` with Ctrl+C.

```bash
docker compose down
```

Add `-v` only when you intend to delete the database volume.

## Troubleshooting

- Startup says the default local database credentials cannot be used: `.env` still has the `reconai` / local-default password while `APP_ENV=demo`. Use `.env.demo.example` on a new volume.
- Startup says debug cannot be enabled: `APP_ENV` is `demo` or `production` and `DEBUG=true`. Set `DEBUG=false`.
- `/ready` is 503: Postgres is down, `DATABASE_URL` does not match the Compose account, or the password in the volume is the one from the first initialization.
- Password authentication failed after an edit to `POSTGRES_PASSWORD`: recreate the volume with `docker compose down -v`, then `docker compose up -d` and `alembic upgrade head`.
- The UI cannot reach the API: API is on port 8000, `NEXT_PUBLIC_API_BASE_URL` is `http://localhost:8000`, and `CORS_ORIGINS` includes `http://localhost:3000`. Restart `npm run dev` after changing `frontend/.env.local`.
- Port 5432 is already in use: stop the other Postgres or do not start a second Compose project.

## Security notes

- No Gemini key is committed. `.env` and `frontend/.env.local` stay untracked.
- Compose falls back to the local development account only when `POSTGRES_PASSWORD` is unset. The demo example uses a different password.
- `APP_ENV=demo` forces debug off.
- Uploads stay on the local disk under `STORAGE_ROOT`, with the existing type and size checks.
- The demo has one operator. Anyone who can reach the API can call it. Do not expose this process to a network you do not control.

## Portfolio limitations

This is a single-machine demo. There is no authentication, no shared tenancy, no worker queue, and no cloud file store. CI passing does not mean the system is ready for real procurement data. Evaluation numbers in `docs/M11_EVALUATION.md` are synthetic.

## Clean-checkout checklist

1. Clone the repository.
2. `python -m venv .venv` and `pip install -r requirements.txt`.
3. Copy `.env.demo.example` to `.env`.
4. Copy `frontend/.env.example` to `frontend/.env.local`.
5. `docker compose up -d`.
6. `alembic upgrade head`.
7. `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
8. `GET /health` returns ok.
9. `GET /ready` returns ready.
10. `cd frontend && npm install && npm run dev`.
11. Open `http://localhost:3000` and load the dashboard.
12. Stop Uvicorn and confirm `/health` no longer answers, then start it again.
