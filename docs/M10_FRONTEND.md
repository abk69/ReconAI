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
| `/exceptions` | Coming later |
| `/risk` | Coming later |
| `/policies` | Coming later |
| `/review` | Coming later |
| `/resolution` | Coming later |

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

## Commands

```bash
cd frontend
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```
