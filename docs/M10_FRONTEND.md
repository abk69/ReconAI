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
| `/dashboard` | Landing page: description, health probe, honest placeholders |
| `/documents` | Coming later |
| `/purchase-orders` | Coming later |
| `/goods-receipts` | Coming later |
| `/invoices` | Coming later |
| `/reconciliation` | Coming later |
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

Feature screens must use this client. Do not hardcode the API origin in components.

No other backend routes are called in M10.1. The backend does not yet send CORS headers; the health probe runs in the browser and will show a clear error until CORS or a same-origin deployment exists. M10.1 does not add a proxy.

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

## Commands

```bash
cd frontend
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```
