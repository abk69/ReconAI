# M15 — Multi-user platform

v1.5.0 adds authentication, tenant boundaries, and durable document processing on top of the v1.0.2 workflow. Deterministic reconciliation is still the financial record. Policy retrieval is still the basis for policy explanations. Extraction stays untrusted until validation and review. Resolution execution still requires a stored human approval.

## Operator setup

Migrations do not create a user and do not attach existing rows to a tenant.

```bash
alembic upgrade head
# Required the first time. Refuses to run once any user exists.
# Do not commit these values. There is no default password.
RECONAI_BOOTSTRAP_EMAIL=owner@example.com RECONAI_BOOTSTRAP_PASSWORD='a long unique passphrase' RECONAI_BOOTSTRAP_TENANT='Northstar' python -m app.identity.bootstrap
```

Then start the API and the worker in separate processes:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.workers
```

The worker claims jobs with `FOR UPDATE SKIP LOCKED` on PostgreSQL and a compare-and-swap update on SQLite. A crashed worker's lease expires after five minutes and the job is scheduled again, up to three attempts. Validation outcomes are successful jobs. A missing document or storage error is not retried. Uploading a file does not queue understanding, promotion, or reconciliation.

The worker writes a poll timestamp every five seconds, including while it is idle. `GET /health/worker` returns `healthy` when the newest poll is within 20 seconds. A poll older than that is `stale` and returns 503. No poll is `unavailable` and returns 503. API liveness stays on `GET /health`. Database readiness stays on `GET /ready`.

## Existing data

Rows from v1.0.2 have `tenant_id` NULL. They stay invisible. Assign them only after choosing the tenant that should own them:

```bash
RECONAI_ASSIGN_LEGACY=yes RECONAI_ASSIGN_TENANT_ID=<tenant-uuid> python -m app.identity.assign_legacy
```

This command is the only supported assignment path. Do not edit the migration to guess a tenant.

## Access

Sessions are random tokens stored as SHA-256 hashes in `user_sessions`. The session cookie is `HttpOnly`. The CSRF cookie is readable so the browser can send `X-CSRF-Token` on unsafe methods. Both are `Secure` when `APP_ENV` is not `local`, `SameSite=Lax`, and expire after 12 hours. Logout revokes the server session and requires `X-CSRF-Token` when the session cookie is still valid. Login allows 8 failures per email hash in 15 minutes, then returns 429.

Roles, from least privilege: viewer (read), operator (upload and request review), reviewer (review, promote, reconcile), approver (plan and approve only), admin (everything, including execute, policy changes, and user provisioning). `POST /auth/users` creates the user in the caller's tenant. The request cannot choose a tenant, a role outside the enum, or an approval.

The frontend signs in at `/login`, sends cookies, and shows job states on the document page. Rendering a page does not enqueue work.

## Observability

HTTP responses keep `X-Request-ID`. A job stores that id as `correlation_id` when it is queued from a request. Worker logs record job id, type, correlation id, attempt, and exception class. They do not record document text, passwords, tokens, or filesystem paths. Failed jobs expose a short `error_message` from the same public sanitizer used by the API. `GET /jobs` returns queue counts for the caller's tenant. `GET /health/worker` reports the newest poll time and does not include document text, tokens, or filesystem paths.

## Limits of this release

- A person can belong to one tenant. Login uses the earliest membership. There is no tenant switch.
- Cross-tenant isolation applies to ORM reads while a tenant is bound, including `session.get` when the row is already in the identity map. Each HTTP request opens a new session. The worker expires its session before each job, then binds that job's tenant. A session with no tenant, including offline evaluation, is unscoped. Direct SQL that bypasses the session is out of scope.
- One worker process runs one job at a time and stops after the current job when it receives Ctrl+C or SIGTERM. It is not a separate queue service. Uploads remain bounded by `max_upload_bytes`.
- There is no public registration and no default administrator password.
