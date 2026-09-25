# ReconAI

Intelligent procurement reconciliation and exception-resolution platform.

## Architectural principle

**Deterministic reconciliation (M2) establishes financial facts.**  
**Document understanding (M4) extracts candidates with provenance — it does not invent financial truth.**  
**Human review (M5) is the trust boundary between candidates and authoritative PO/GRN/Invoice data.**  
**Gemini (M6) may assist extraction — it never writes financial truth.**  
**Grounded policy RAG (M7.4) explains retrieved policy evidence — it never overrides M2.**  
**Controlled agentic resolution (M8) may propose typed workflow actions — never freely mutate financial records.**  
**Anomaly intelligence (M9) emits explainable risk signals — never fraud determinations or financial mutations.**

## Milestones

| Milestone | Status |
| --- | --- |
| M0 Foundation | Done |
| M1 Persistence | Done |
| M2 Deterministic reconciliation | Done |
| M3 Document + structured intake | Done |
| M4 Deterministic document understanding | Done |
| M5 Extraction evaluation + human review | Done |
| M6 Real LLM-assisted extraction (Gemini) | Done |
| M7.1 Policy knowledge-base foundation | Done |
| M7.2 Policy ingestion & chunking | Done |
| M7.3 Embeddings + vector retrieval | Done |
| M7.4 Grounded Gemini policy reasoning | Done |
| M7.5 RAG evaluation + grounding quality | Done |
| M8.1 Agentic resolution architecture | Done |
| M8.2 Tool registry + safe action handlers | Done |
| M8.3 AI resolution planner | Done |
| M8.4 Human approval gate | Done |
| M8.5 Controlled action execution | Done |
| M8.6 Audit trail & observability | Done |
| M8.7 Agent evaluation | Done |
| **M8 Agentic resolution** | **Complete** |
| M9.1 Anomaly detection foundation | Done |
| M9.2 Batch detection & analytics | Done |
| M9.3 Transparent risk scoring | Done |
| M10.1 Next.js dashboard foundation | Done |
| M10.2 Executive dashboard | Done |
| M10.3 Procurement reconciliation workspace | Done |
| M10.4 Exception and human review center | Done |
| M10.5 Risk and anomaly intelligence | Done |
| M10.6 Document intelligence | Done |
| M10.7 Policy intelligence | Done |
| M10.8 Visual system | Done |
| M10.9 Frontend production readiness | Done |
| M10.10 Document intake UI | Done |
| M11.1 Extraction evaluation | Done |
| M11.2 RAG and grounding evaluation | Done |
| M11.3 Agent safety evaluation | Done |
| M11.4 Security and prompt-injection evaluation | Done |

The dashboard shell lives in [`frontend/`](frontend/). See [`docs/M10_FRONTEND.md`](docs/M10_FRONTEND.md).

## M9.3 — Transparent risk scoring

Deterministic 0–100 risk-signal bands from anomaly signals — **not fraud
probabilities**. Explainable breakdown + versioned immutable profiles.

```bash
GET /risk/vendors/{vendor_id}
GET /risk/invoices/{invoice_id}
GET /risk/purchase-orders/{purchase_order_id}
```

See [`docs/M9_ANOMALY_INTELLIGENCE.md`](docs/M9_ANOMALY_INTELLIGENCE.md).

## M9.2 — Batch detection & analytics

Bounded, resumable anomaly scans + SQL analytics (not fraud scores).

```bash
POST /anomalies/scans
POST /anomalies/scans/{scan_id}/run
GET  /anomalies/summary
GET  /anomalies/trends?period=daily
```

See [`docs/M9_ANOMALY_INTELLIGENCE.md`](docs/M9_ANOMALY_INTELLIGENCE.md).

## M9.1 — Anomaly detection foundation

Deterministic procurement **anomaly signals** (not fraud determinations).
No LLM. No financial mutation. No action execution.

```bash
POST /anomalies/detect/invoice/{invoice_id}
POST /anomalies/detect/vendor/{vendor_id}
GET  /anomalies
```

See [`docs/M9_ANOMALY_INTELLIGENCE.md`](docs/M9_ANOMALY_INTELLIGENCE.md).

## M8.7 — Agent evaluation

Offline deterministic harness (`FakeResolutionPlannerLLM`) scores planner
safety and validity. Numbers are **harness correctness**, not Gemini quality.

```bash
python -m app.evaluation.m8_runner
python -m app.evaluation.m8_runner --live   # optional, needs GEMINI_API_KEY
```

See [`docs/M8_AGENTIC_RESOLUTION.md`](docs/M8_AGENTIC_RESOLUTION.md).

## M8.6 — Audit trail & observability

Append-only lifecycle events reconstruct plan → approval → execution → workflow.

```bash
GET /resolution-plans/{plan_id}/audit
```

See [`docs/M8_AGENTIC_RESOLUTION.md`](docs/M8_AGENTIC_RESOLUTION.md).

## M8.5 — Controlled action execution

Deterministic registry dispatch after human approval. **LLM never executes.**

```bash
POST /resolution-plans/{plan_id}/actions/{action_id}/execute
```

Body: `{ "idempotency_key": "..." }`. Guardrails + savepoint + idempotency.
Workflow records only — no financial mutation.

See [`docs/M8_AGENTIC_RESOLUTION.md`](docs/M8_AGENTIC_RESOLUTION.md).

## M8.4 — Human approval gate

Humans authorize proposed actions. **Approval does not execute the action.**

```bash
POST /resolution-plans/{plan_id}/actions/{action_id}/approve
POST /resolution-plans/{plan_id}/actions/{action_id}/reject
```

Body: `{ "reviewer": "...", "comment": "..." }`. Reviewer identity is
application-supplied (auth integrates later). Duplicate decisions are
idempotent. Execution remains a separate step.

See [`docs/M8_AGENTIC_RESOLUTION.md`](docs/M8_AGENTIC_RESOLUTION.md).

## M8.3 — AI resolution planner

Gemini proposes registered workflow actions only. Application validates against
typed contracts + ActionRegistry, then persists a `ResolutionPlan`. Humans
still approve; M8.2 handlers still execute. **No financial mutation.**

```bash
POST /reconciliation/exceptions/{exception_id}/resolution-plan
```

See [`docs/M8_AGENTIC_RESOLUTION.md`](docs/M8_AGENTIC_RESOLUTION.md).

## M8.2 — Safe action handlers

Real deterministic handlers create durable workflow records (review route,
vendor clarification, missing document, manager escalation). No email, no
financial mutations, no LLM agent.

```bash
POST /resolution-plans/{plan_id}/actions/{action_id}/execute
```

Requires prior approval when `requires_approval` is true. Body:
`{ "idempotency_key": "..." }`. Stored action parameters are authoritative.

See [`docs/M8_AGENTIC_RESOLUTION.md`](docs/M8_AGENTIC_RESOLUTION.md).

## M8.1 — Agentic resolution architecture

Controlled pipeline only — **no LLM agent execution yet**:

```
Exception → ResolutionPlan → ProposedAction(s)
         → Guardrails → Human Approval → Execution → Audit
```

Initial actions are workflow-only (`ROUTE_TO_REVIEW`, vendor clarification,
missing document, escalate). Financial mutation actions are explicitly out of
scope. Approval APIs record decisions; they do not silently execute.

```bash
GET  /resolution-plans/{plan_id}
GET  /resolution-plans/{plan_id}/actions
POST /resolution-plans/{plan_id}/actions/{action_id}/approve
POST /resolution-plans/{plan_id}/actions/{action_id}/reject
POST /resolution-plans/{plan_id}/actions/{action_id}/execute
GET  /resolution-plans/{plan_id}/executions
```

## M7.1 — Policy knowledge-base foundation

Policy guidance is stored separately from procurement transactions so future RAG can cite **versioned** policy text without mixing knowledge into M2 financial tables.

```
PolicyDocument
  └── PolicyVersion (label, effective dates, content_hash, status)
        └── PolicyChunk (ordered text + section/page provenance + optional embedding)
```

### M7.2 — Ingestion & chunking

```bash
POST /policies/{policy_id}/versions/{version_id}/ingest
```

Accepts Markdown or PDF. Deterministic section-aware chunking (`POLICY_CHUNK_MAX_CHARS`). Identical source re-ingest is idempotent.

### M7.3 — Embeddings + retrieval

PostgreSQL **pgvector** stores L2-normalized vectors on `PolicyChunk` (derived from content). Default model: `gemini-embedding-001` at **768** dims (`EMBEDDING_MODEL` / `EMBEDDING_DIMENSION`). Cosine distance ranking; no ANN index at portfolio scale. Embedding is explicit — not on GET.

```bash
POST /policies/{policy_id}/versions/{version_id}/embed
POST /policies/{policy_id}/versions/{version_id}/search
```

Docker DB image: `pgvector/pgvector:pg16`.

### M7.4 — Grounded policy explanation

RAG over retrieved chunks only. M2 remains financial authority; Gemini explains policy implications with validated citations. Weak/empty retrieval → `INSUFFICIENT_EVIDENCE` (no general-knowledge answers). Multiple ACTIVE versions of the same document → `CONFLICTING_POLICY`.

```bash
POST /reconciliation/exceptions/{exception_id}/policy-explanation
```

See [`docs/M7_POLICY_KB.md`](docs/M7_POLICY_KB.md).

### M7.5 — Evaluation

Retrieval and grounding are scored **separately** (Hit@3 / Recall@3 / MRR vs citation precision / fact accuracy / abstention). No single RAG score.

```bash
python -m app.evaluation.m7_runner
python -m app.evaluation.m7_runner --live   # optional, needs GEMINI_API_KEY
```

### API (M7.1 storage)

```bash
POST /policies
GET  /policies
GET  /policies/{policy_id}
POST /policies/{policy_id}/versions
GET  /policies/{policy_id}/versions
GET  /policies/{policy_id}/versions/{version_id}
POST /policies/{policy_id}/versions/{version_id}/chunks
GET  /policies/{policy_id}/versions/{version_id}/chunks
POST /policies/{policy_id}/versions/{version_id}/ingest
POST /policies/{policy_id}/versions/{version_id}/embed
POST /policies/{policy_id}/versions/{version_id}/search
```

## M6 — Real Gemini-assisted extraction

M4 remains the deterministic baseline. Gemini (`gemini-3.1-flash-lite` via official `google-genai` SDK) is invoked **only** when the quality gate says M4 needs help. Structured JSON Schema output is validated with Pydantic, grounded against document evidence, compared to M4, and sent to M5 review. **Gemini never writes PO/GRN/Invoice rows.**

```
M4 candidate
   │
   ├─ READY_FOR_RECONCILIATION → skip Gemini (cost control)
   │
   └─ REVIEW_REQUIRED / UNKNOWN / OCR / missing fields
          → Gemini structured extraction
          → schema + evidence + business validation
          → M4 vs Gemini comparison
          → LlmExtractionResult (separate from M4)
          → M5 ReviewTask
          → PromotionService → authoritative data → M2
```

### Interview concepts

| Concept | How ReconAI applies it |
| --- | --- |
| LLM as probabilistic component | Gemini produces *candidates*, not facts |
| Deterministic guardrails | M4 gate, validator, evidence match, M5, M2 |
| Structured output | `response_schema=GeminiExtractionOutput` |
| Schema validation | Pydantic after provider response |
| Grounding / evidence | Snippet must appear in document text |
| Hallucination mitigation | Unsupported values → REVIEW_REQUIRED |
| Human-in-the-loop | M5 approve/correct/reject + promote |
| Cost-aware inference | Skip Gemini when M4 is ready; truncate context |
| Provider abstraction | `LLMProvider` / `GeminiProvider` |
| Observability | Token usage metadata when returned |
| Evaluation | Golden vs M4 vs Gemini (`python -m app.evaluation.m6_runner`) |

### API

```bash
POST /documents/{id}/llm-understand
GET  /documents/{id}/llm-understanding
```

### Configuration

```bash
GEMINI_API_KEY=           # required for live calls; never commit
LLM_PROVIDER=google
LLM_MODEL=gemini-3.1-flash-lite
LLM_TIMEOUT_SECONDS=45
LLM_MAX_INPUT_CHARS=24000
LLM_MAX_OUTPUT_TOKENS=4096
LLM_MAX_RETRIES=1
```

### Tests

```bash
pytest -q                     # offline suite (excludes live_* markers)
pytest -m live_llm -q         # opt-in real Gemini extraction (needs GEMINI_API_KEY)
pytest -m live_embedding -q   # opt-in real Gemini embeddings (needs GEMINI_API_KEY)
pytest -m live_grounding -q   # opt-in grounded policy RAG (needs GEMINI_API_KEY)
pytest -m live_rag_eval -q    # opt-in M7.5 live RAG smoke (needs GEMINI_API_KEY)
pytest -m live_resolution_eval -q  # opt-in M8.7 live planner smoke (needs GEMINI_API_KEY)
python -m app.evaluation.m6_runner
python -m app.evaluation.m7_runner
python -m app.evaluation.m8_runner
python -m app.evaluation.m6_runner --live
python -m app.evaluation.m7_runner --live
python -m app.evaluation.m8_runner --live
```

Behavior matrix for interviews: [`docs/M6_BEHAVIOR.md`](docs/M6_BEHAVIOR.md).

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
