# M10.1 — Frontend foundation

The Next.js application lives in `frontend/` so it does not collide with the Python package `app/`.

## Stack

- Next.js (App Router)
- TypeScript (strict)
- Tailwind CSS v4
- ESLint (`eslint-config-next`)
- `lucide-react` for the mobile menu icon only

Package manager: npm.

## Application shell

Desktop: persistent left sidebar, top header, main content.

Below the `lg` breakpoint the sidebar collapses into a button-controlled navigation region. The control is a `<button>`. Section links are `<a>` via Next.js `Link`.

## Routes

| Path | M10.1 content |
| --- | --- |
| `/` | Redirects to `/dashboard` |
| `/dashboard` | Executive dashboard from `GET /dashboard/summary` |
| `/documents` | Document list and detail |
| `/purchase-orders` | Purchase order list and detail |
| `/goods-receipts` | Goods receipt list and detail |
| `/invoices` | Invoice list and detail |
| `/reconciliation` | Persisted reconciliation exceptions |
| `/exceptions` | Exception queue |
| `/risk` | Risk and anomaly intelligence |
| `/policies` | Policy library, version detail, and retrieval |
| `/review` | Extraction review center |
| `/resolution` | Resolution plans |

Navigation is defined once in `frontend/lib/navigation.ts`.

## Components

- `components/layout` — shell and header
- `components/navigation` — sidebar
- `components/ui` — loading, error, empty, skeleton, status badges, section placeholders
- `components/dashboard` — system status probe

## API client

- `lib/config/env.ts` reads `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).
- `lib/api/config.ts` holds base URL and timeout.
- `lib/api/client.ts` performs JSON requests with abort and timeout, and raises `ApiError`.
- `lib/api/health.ts` calls the existing `GET /health` endpoint.
- `lib/api/dashboard.ts` calls `GET /dashboard/summary`.

Feature screens must use this client. Do not hardcode the API origin in components.

## Environment

Copy `frontend/.env.example` to `frontend/.env.local` when the API origin is not the default.

`NEXT_PUBLIC_*` values are visible in the browser. Do not place Gemini keys, database credentials, or other secrets there.

## Design

Light enterprise surface: neutral canvas, white cards, hairline borders, small shadows. Semantic tones: success, warning, danger, info, neutral. Risk bands `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` use those tones plus the band text. Color is never the only signal.

## Authentication

No login or authorization exists. The API client leaves room for an `Authorization` header later. The UI does not pretend a user is signed in.

## Relationship to backend layers

Deterministic reconciliation (M2) is the source of financial facts. Anomaly detection and risk scoring (M9) are explainable signals, not fraud decisions. Policy reasoning (M7) is grounded explanation. Resolution planning (M8) proposes actions that still require human approval.

Frontend presentation must distinguish deterministic financial facts, anomaly/risk signals, policy-grounded explanations, and AI-assisted recommendations.

## M10.2 — Executive dashboard

The dashboard reads `GET /dashboard/summary`. The browser does not count records or derive financial totals.

### Endpoint

Read-only. It does not run reconciliation, anomaly detection, risk scoring, Gemini, or resolution.

Returned groups:

| Field | Source |
| --- | --- |
| `documents` | `documents.status` counts |
| `reconciliation_exceptions` | persisted exception status counts |
| `open_exceptions` | newest `OPEN` and `IN_REVIEW` exceptions, with invoice, PO, and GRN numbers when linked |
| `anomaly_signals` | persisted anomaly signal severity counts |
| `risk_profiles` | latest persisted profile per entity and score version, counted by `risk_band` |
| `review_tasks` / `pending_reviews` | M5 review task statuses; pending rows include the document filename |
| `recent_activity` | bounded rows from documents, exceptions, review decisions, anomaly signals, risk profiles, and resolution audit events |

Successful reconciliation matches are not stored as their own records, so the API does not report a matched-run total. Risk profiles are not recalculated. Historical profiles for the same entity are not all counted; the latest `as_of` row is used.

`risk_note` states that risk scores are deterministic aggregations of anomaly signals and are not fraud probabilities.

### Frontend behavior

One summary request feeds every card. Refresh is a manual button. It does not poll.

- First load shows a loading state.
- A failed refresh keeps the last successful summary and shows an error.
- Zero counts and empty lists are empty states, not errors.
- If the API cannot be reached, the shell stays up and the data region shows that the backend is unavailable.

Browser calls need `CORS_ORIGINS` to include the frontend origin (default `http://localhost:3000`). That is not a proxy and does not send credentials.

### Metrics and layers

Document status, reconciliation exception status, and review status are persisted workflow facts. Anomaly severities and risk bands are M9 signals. The dashboard does not present risk bands as fraud findings, and it does not present extraction or AI text as financial truth.

Frontend presentation must distinguish deterministic financial facts, anomaly/risk signals, policy-grounded explanations, and AI-assisted recommendations.

## M10.3 — Procurement reconciliation workspace

Lists and details read persisted records. The browser does not run reconciliation, sum line amounts into a new total, or call Gemini.

### Endpoints

| Method | Purpose |
| --- | --- |
| `GET /documents` | Existing list, plus optional `q`, `limit`, and `offset`. `total` is the filtered count. |
| `GET /documents/{id}` | Existing detail |
| `GET /purchase-orders` | New list. `q` matches PO number. `status`, `vendor_id`, `limit`, `offset` |
| `GET /purchase-orders/{id}` | Existing detail, including stored lines |
| `GET /goods-receipts` | New list. `q` matches GRN number. `purchase_order_id` filter |
| `GET /goods-receipts/{id}` | Existing detail |
| `GET /invoices` | New list. `q` matches invoice number. Stored `total_amount` is returned as stored |
| `GET /invoices/{id}` | Existing detail |
| `GET /vendors/{id}` | Existing vendor name lookup |
| `GET /reconciliation/exceptions` | Persisted exceptions. Filters: `q` (invoice, PO, or GRN number), `status`, `severity`, `exception_type`, and foreign keys |
| `GET /reconciliation/exceptions/{id}` | Exception message plus stored evidence |

`counts_by_status` ignores the status filter so the summary chips stay stable while the table is filtered. Search is a case-insensitive contains match on identifiers, not fuzzy or AI search.

Pagination is `limit`/`offset`. The UI keeps filters in the query string, so browser back returns to the same list.

### Presentation

Exception detail labels the message as a deterministic reconciliation fact and renders evidence fields as stored. Raw JSON is behind a disclosure. Policy explanation and resolution planning are not requested.

Related purchase orders, goods receipts, invoices, and exceptions are linked only when the API returns those ids.

Empty lists and “backend unavailable” stay separate. A zero total is an empty state.

## M10.4 — Exception and human review center

The exception queue, extraction review center, and resolution center read persisted records. The browser does not re-run reconciliation, extraction, policy grounding, or resolution planning.

### APIs

Existing reads and actions:

- `GET /reconciliation/exceptions` and `GET /reconciliation/exceptions/{id}`
- `GET/POST /review/tasks` including approve, correct, reject, and promote
- `GET /resolution-plans/{id}` plus actions, executions, audit, approve, reject, and execute

Added reads, without new workflow rules:

- `GET /review/tasks` accepts optional `q`, `limit`, and `offset`. Omitting `limit` still returns the full filtered queue. `total` is the filtered count.
- `GET /resolution-plans` lists persisted plans. Optional `status` and `reconciliation_exception_id`.
- `GET /resolution-plans/{id}/approvals` lists immutable human approval rows.
- `GET /reconciliation/exceptions/{id}/policy-grounding` returns stored explanations only. It does not call Gemini and does not return provider metadata.

### Exception workflow

`/exceptions` is the operational queue. Filters are sent to the existing exception list. `/exceptions/{id}` shows the stored message as the reconciliation fact, stored evidence, source records, document ids, exception status, stored policy grounding, and links to resolution plans.

If no grounding row exists, the page says policy grounding is unavailable. AI explanation text is labeled as an AI-assisted policy explanation and is kept separate from the fact.

### Review workflow

`/review` lists M5 tasks. Pending and in-review rows are marked as needing a person. `/review/{id}` shows the source document, the original extraction candidate, the reviewed candidate when one exists, stored evidence, and append-only decisions.

Extracted values, reviewed values, and a promoted procurement record are separate sections. Promotion is the point at which the backend creates authoritative data.

Approve, reject, correct, and promote call the existing M5 routes. The page waits for the response, shows that result, then reloads the task. It does not mark those actions successful before the API responds. Approve, reject, promote, and correction each use a confirmation that names the action.

The correction form only includes editable fields present on the stored candidate, including line paths such as `lines[0].quantity`. The backend validates the values.

### Resolution workflow

`/resolution` lists stored plans in the order plan, actions, approval, execution, result. `/resolution/{id}` shows the proposal and its limitations as an AI-proposed plan, action type, stored parameters, whether approval is required, approval rows, executions, and the audit trail.

Approve and reject record a human decision and do not execute. Execute is offered only when the loaded action is already approved, or when the stored action does not require approval and is still pending. The execute request sends an idempotency key only. Parameters shown in the confirmation are the stored parameters. A rejected action does not get an execute button.

Audit events show event type, actor type (`SYSTEM`, `LLM`, or `HUMAN`), actor, time, and event data. LLM events are labeled as actor type LLM and are not described as authorization. Metadata keys that look like secrets are redacted in the browser in addition to backend sanitization.

### Mutation behavior

Consequential actions require an explicit click and a confirmation that names the action. Success text comes from the API response. The screen then reloads authoritative state. Approval, rejection, promotion, and execution are not applied optimistically.

## M10.5 — Risk and anomaly intelligence

`/risk` presents stored M9 anomaly signals and risk profiles. The browser does not score entities, detect anomalies, or call Gemini.

### APIs

Existing reads:

- `GET /anomalies` with cursor pagination and filters for type, severity, vendor, invoice, purchase order, and detected time
- `GET /anomalies/{id}`
- `GET /anomalies/summary` and `GET /anomalies/trends`
- `GET /risk/vendors/{id}`, `GET /risk/invoices/{id}`, and `GET /risk/purchase-orders/{id}` calculate a profile when one is missing. The workspace does not call those routes.

Added reads:

- `GET /risk/profiles` returns the latest stored profile per entity and score version, matching the dashboard rule of maximum `as_of`. `counts_by_band` uses that same set.
- `GET /risk/profiles/{entity_type}/{entity_id}` returns the stored current profile and immutable history. Optional `as_of` selects one stored date. A missing date returns `current: null` and does not calculate a score.
- `GET /anomalies/scans` lists stored scan jobs.
- `GET /anomalies?high_or_critical=true` limits the list to HIGH and CRITICAL when a single severity is not also set.

### Routes

| Path | Content |
| --- | --- |
| `/risk` | Band summary, anomaly counts, high-priority signals, anomaly queue, trends, scan jobs |
| `/risk/vendors/[id]` | Stored vendor profile, breakdown, history, vendor-scoped signals |
| `/risk/invoices/[id]` | Stored invoice profile and invoice-scoped signals |
| `/risk/purchase-orders/[id]` | Stored purchase-order profile and purchase-order-scoped signals |
| `/risk/anomalies/[id]` | One stored anomaly signal and its evidence |

### Presentation

An anomaly is a deterministic M9 signal. A risk score is a deterministic aggregation of those signals for one entity. Scores are shown as `Risk score: 78` with the stored signal count. The page states that scores are not fraud probabilities.

Detail pages render `breakdown.contributing_signals` and `breakdown.type_breakdown` as stored. They do not recompute weights or caps. A fingerprint is labeled as a stable record identity.

`as_of` is labeled point-in-time risk. A stored score of 0 is shown as that score. A date with no stored row says no profile is stored for that point in time. Historical rows stay in the history list and are not described as recalculated.

Scan jobs are read-only. Trend rows are only the periods the analytics API returns.

## M10.6 — Document intelligence

`/documents` and `/documents/{id}` present the stored path from intake through extraction, review, and promotion. The browser does not extract, validate, score confidence, or call Gemini.

### Trust boundary

A stored document can have an extraction candidate, a validation result, a human review task, and a promoted procurement record. Those are different objects. The candidate is labeled as a candidate. The promoted invoice, purchase order, or goods receipt is the authoritative record, and only when the review task stores a promotion target.

### APIs

Existing reads:

- `GET /documents` and `GET /documents/{id}`
- `GET /documents/{id}/understanding`
- `GET /documents/{id}/llm-understanding`
- `GET /review/tasks` and `GET /review/tasks/{id}`

Added reads:

- `GET /documents` now includes stored `detected_type`, `extraction_outcome`, and `review_status` for each row. Null means no stored extraction or review row. Optional filters `extraction_outcome` and `review_status` are applied in the database.
- `GET /documents/{id}/raw-extraction` returns the stored raw extraction when the disclosure is opened. Keys that look like storage paths or secrets are omitted.
- `GET /review/tasks?document_id=` limits the queue to one document.

`storage_path` remains on the document API response and is not shown. SHA-256, MIME type, extension, and size are shown as stored file metadata. There is no document preview and no upload control.

`POST /documents/{id}/understand` and `POST /documents/{id}/llm-understand` are not called by this workspace.

### Lifecycle

The header shows the stored document status by name. A separate derived workflow view marks Intake, Validated, Understanding, Extracted, Review, Approved or corrected, Promoted, and Ready for reconciliation from that status and from stored extraction, review, and promotion rows. Missing stages say that no row is stored. They are not errors. Times appear only when the record stores them.

### M4, M5, and M6

The extraction section shows the stored candidate, outcome, extractor version, validation issues, and field evidence. Page, source, and snippet say unavailable when the evidence row does not include them. Raw candidate, validation, evidence, and raw extraction stay inside disclosures.

Review status, reviewer, decisions, and an Open review link go to `/review/{id}`. This page does not approve, correct, reject, or promote.

Gemini-assisted extraction shows provider, model, prompt version, invocation status, application quality, quality-gate reasons, stored comparison, evidence check, and token usage when those fields are stored. Comparison rows are the persisted agreements and disagreements. The page does not choose a correct candidate. Provider metadata and API keys are not requested.

## M10.7 — Policy intelligence

`/policies` replaces the placeholder. The browser reads stored policy documents, versions, and chunks. It does not embed text, call Gemini, or decide which policy applies.

### Library and versions

`GET /policies` returns each document with stored version counts. `active_version_label` and `active_status` are set only when exactly one version is `ACTIVE`. Several active versions stay unresolved. Optional `version_status`, `limit`, and `offset` filter and page that list. Omitting `limit` still returns the full filtered list.

`/policies/{id}` lists versions with status, effective dates, source filename, and chunk count. `/policies/{id}/versions/{versionId}` shows one version and its chunks. Chunk text is labeled policy data. It is quoted source content, including text that looks like an instruction.

`ACTIVE` is the stored version status. Effective dates remain visible.

### Retrieval

Search is an explicit submit on the version page. It calls the existing `POST /policies/{id}/versions/{versionId}/search`. Similarity is labeled as a retrieval signal. A retrieval result is not a grounded conclusion. The page does not search on load.

### Grounding and resolution

`/exceptions/{id}` keeps section-level loads for stored policy grounding and resolution plans. It does not call `POST …/policy-explanation` or `POST …/resolution-plan`.

Grounding status is shown as stored: `SUPPORTED`, `INSUFFICIENT_EVIDENCE`, `CONFLICTING_POLICY`, or `PROVIDER_ERROR`. Insufficient evidence is abstention, not an error. A conflict lists the cited versions and does not pick one. A provider error says the explanation could not be generated. Citations render only the fields stored on the grounding result, with links when policy and version ids are present. An empty grounding list says no grounding is stored.

A stored resolution plan is labeled AI-proposed. The exception page shows the reasoning summary, limitations, action type, stored parameters, approval requirement, and status, then links to `/resolution/{id}` for approval and execution.

The page states the chain: reconciliation fact, policy evidence, AI-assisted explanation, AI-proposed resolution, human approval.

## Commands

```bash
cd frontend
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```
