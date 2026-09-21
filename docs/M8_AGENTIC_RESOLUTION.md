# M8 — Agentic Resolution

M8 introduces **controlled** agentic resolution. An agent may propose workflow
actions; it must never freely modify the database or financial records.

## M8.1 scope

M8.1 is **domain architecture and persistence only**.

| Included | Not included |
| --- | --- |
| ResolutionPlan / ProposedAction / ActionApproval / ActionExecution | LLM agent loop |
| Typed action contracts + ActionRegistry | Gemini tool calling |
| Deterministic guardrails | Automatic financial changes |
| Human approval APIs | MODIFY_INVOICE / MODIFY_PO / DELETE_* / APPROVE_PAYMENT |
| Idempotent execution records | Silent execute-on-approve |

## M8.2 scope — Tool registry + safe action handlers

M8.2 turns the four M8.1 placeholders into **real deterministic handlers** that
create durable workflow records only.

| Included | Still not included |
| --- | --- |
| Typed parameter contracts (strict) | LLM agent / Gemini tool calling |
| Real handlers under `app/resolution/handlers/` | Email / Slack / HTTP notifications |
| Workflow tables for route / clarification / missing doc / escalation | Financial mutations |
| Execute API endpoint | Autonomous planning |
| Optional M5 `ReviewTask` link on ROUTE_TO_REVIEW | Arbitrary `execute_tool` |

### Four real safe actions

| Action | Workflow record | Notes |
| --- | --- | --- |
| `ROUTE_TO_REVIEW` | `exception_review_routes` | Exception-scoped review routing; optional M5 `ReviewTask` when document+extraction IDs supplied |
| `REQUEST_VENDOR_CLARIFICATION` | `vendor_clarification_requests` | No email — durable request only |
| `REQUEST_MISSING_DOCUMENT` | `missing_document_requests` | No external contact |
| `ESCALATE_TO_MANAGER` | `manager_escalations` | No manager notification |

Each handler returns a structured `ActionResult` with `status`, `reference_id`,
and `message`. One successful `ProposedAction` maps to at most one workflow row
(`proposed_action_id` unique).

### Typed parameters (M8.2)

- `ROUTE_TO_REVIEW`: `review_queue`, optional `reason` / `assigned_to` / M5 IDs
- `REQUEST_VENDOR_CLARIFICATION`: `question` + `vendor_id` **or** `vendor_reference`; optional `reason` / `fields` / `due_date`
- `REQUEST_MISSING_DOCUMENT`: `document_type`, `reason`; optional vendor refs
- `ESCALATE_TO_MANAGER`: `reason`, `priority`, optional `destination`

Unknown fields are rejected (`extra="forbid"`).

### Execution lifecycle (M8.2)

```
validate (registry, params, plan, approval, idempotency)
    ↓
create ActionExecution (PENDING → RUNNING)
    ↓
handler in savepoint → workflow row
    ↓
SUCCEEDED + structured result   OR   FAILED + structured error
```

Handler side effects run in a nested savepoint so a failure rolls back the
business row while preserving the FAILED execution audit record. Failed
actions may be retried with a new idempotency key (`FAILED → EXECUTING`).

### What actions still CANNOT do

- Modify invoice / PO / GRN financial values
- Approve payment or delete transactions
- Execute SQL, shell, URLs, or dynamic Python
- Accept arbitrary JSON as an executable tool contract
- Send email or call external APIs
- Bypass approval or stored ProposedAction parameters

There is still **no LLM agent**.

## Why controlled actions

Procurement reconciliation touches money. An unconstrained agent that can call
arbitrary tools or mutate PO/GRN/Invoice rows would bypass:

- **M2** deterministic financial truth
- **M5** human promotion trust boundary
- **M7** grounded policy explanation (advisory only)

M8 therefore uses an explicit pipeline:

```
Exception
    ↓
ResolutionPlan          (what the agent proposes)
    ↓
ProposedAction(s)       (concrete, typed workflow steps)
    ↓
Validation / Guardrails (deterministic — never Gemini)
    ↓
Human Approval          (ActionApproval audit row)
    ↓
Execution               (ActionExecution + idempotency key)
    ↓
Result                  (preserved, append-only audit)
```

**Architectural invariant:** the future agent may propose actions. Only
validated, explicitly registered actions may execute. Approval-required
actions require explicit human approval. The LLM never directly modifies
financial records.

## Lifecycle / state machines

### ResolutionPlanStatus

`PROPOSED` → `APPROVAL_REQUIRED` → `APPROVED` → `EXECUTING` → `COMPLETED`

Also: `REJECTED`, `FAILED`, `CANCELLED` (terminal).

Plans never write financial facts. They only coordinate workflow actions.

### ProposedActionStatus

`PENDING` → `APPROVED` | `REJECTED` → (`APPROVED` →) `EXECUTING` → `COMPLETED` | `FAILED`

### ExecutionStatus

`PENDING` → `RUNNING` → `SUCCEEDED` | `FAILED`

## Allowed initial action types (M8.1)

| ActionType | Purpose |
| --- | --- |
| `ROUTE_TO_REVIEW` | Send exception to a review queue |
| `REQUEST_VENDOR_CLARIFICATION` | Ask vendor about disputed fields |
| `REQUEST_MISSING_DOCUMENT` | Request a missing supporting document |
| `ESCALATE_TO_MANAGER` | Escalate to a manager role |

These orchestrate **workflow**, not financial truth.

## Explicitly forbidden (out of scope)

- `MODIFY_INVOICE` / `MODIFY_PO` / `MODIFY_GRN`
- `DELETE_TRANSACTION` / delete of procurement rows
- `APPROVE_PAYMENT`
- Generic `execute_tool(name, arbitrary_json)` without typed registration

## Action contracts + registry

Parameters are untrusted input. Every executable action must:

1. Be an `ActionType` enum member
2. Be registered in `ActionRegistry`
3. Validate parameters with a Pydantic schema (`extra="forbid"`)
4. Expose `requires_approval` and `execute()`

There is no path for arbitrary function names, SQL, shell commands, URLs, or
Python expressions to become executable.

M8.1 handlers were **placeholders**. M8.2 registers real handlers via
`build_default_registry()` — still explicit registration only; no dynamic
function discovery.

## Human approval boundary

- `POST /resolution-plans/{plan_id}/actions/{action_id}/approve`
- `POST /resolution-plans/{plan_id}/actions/{action_id}/reject`

These endpoints **only persist** `ActionApproval` decisions. They do **not**
execute the action.

Guardrails reject execution when:

- the action requires approval and no `APPROVED` record exists
- the latest approval decision is `REJECTED`
- the plan is `CANCELLED` / `REJECTED` / other non-executable status
- the action type is unknown / unregistered
- parameters fail the typed schema
- an idempotency key would create a duplicate unsafe execution

## Idempotency

Each `ActionExecution` has a required `idempotency_key` with a **database
unique constraint** (`uq_action_executions_idempotency_key`).

Retrying with the same key returns the existing execution. A different key
cannot start a second active/successful run of the same proposed action.

## Audit design

Traceability chain:

```
ReconciliationException
  → ResolutionPlan (proposed_by, reasoning_summary, optional policy_grounding_result_id)
    → ProposedAction (type, order, parameters, rationale)
      → ActionApproval (decision, reviewer, reason, decided_at)  # append-only
      → ActionExecution (status, result / error, timestamps, idempotency_key)
          → ExceptionReviewRoute | VendorClarificationRequest
            | MissingDocumentRequest | ManagerEscalation
```

FK policy for audit safety:

- `resolution_plans.reconciliation_exception_id` → **RESTRICT**  
  Deleting an exception cannot silently destroy resolution audit rows.
- Optional `policy_grounding_result_id` → **SET NULL**
- Plan → actions → approvals/executions cascade within the plan tree
- Workflow request tables → exception / proposed_action **RESTRICT**; unique on `proposed_action_id`

Historical approval decisions are never overwritten; new rows are appended.

## API

```bash
GET  /resolution-plans/{plan_id}
GET  /resolution-plans/{plan_id}/actions
POST /resolution-plans/{plan_id}/actions/{action_id}/approve
POST /resolution-plans/{plan_id}/actions/{action_id}/reject
POST /resolution-plans/{plan_id}/actions/{action_id}/execute
GET  /resolution-plans/{plan_id}/executions
```

`execute` requires `{ "idempotency_key": "..." }`. Stored ProposedAction
parameters are authoritative — callers cannot inject alternate parameters.
Approval remains a separate step and never silently executes.

## Relationship to earlier milestones

| Milestone | Role vs M8 |
| --- | --- |
| M2 | Remains financial authority — unchanged by resolution execution |
| M4/M6 | Extraction candidates — unchanged |
| M5 | Human promotion boundary for documents — separate from M8 action approval |
| M7 | Policy grounding may be referenced on a plan — never mutated by M8 |

## M8.3 — AI Resolution Planner

**The model proposes; the application validates; the human authorizes; the executor performs.**

```
Exception
  → deterministic M2 facts
  → optional M7 policy grounding
  → Gemini planner (structured JSON only)
  → schema + registry + typed contract validation
  → ResolutionPlan + ProposedAction(s)
  → human approval (M8.1/M8.2)
  → execution (M8.2 handlers)
```

Gemini is a **planner**, never an executor. It cannot call tools, approve actions,
mutate financial records, send email, or invent action types outside:

`ROUTE_TO_REVIEW` | `REQUEST_VENDOR_CLARIFICATION` | `REQUEST_MISSING_DOCUMENT` | `ESCALATE_TO_MANAGER`

### Prompt trust boundaries

| Section | Trust |
| --- | --- |
| System instructions + constraints | Trusted |
| Reconciliation facts (M2) | Trusted |
| Grounding metadata (status/conclusion IDs) | Trusted application summary |
| Policy explanation / citations / vendor text | **Untrusted data** |
| Available action contracts | Trusted allowlist |

### Planning idempotency

`planning_key = sha256(exception_id | grounding_id | planner_version | prompt_version | model)`  
Unique on `resolution_plans.planning_key`. Same context returns the existing plan unless `force_replan=true`.

### Planning API

```bash
POST /reconciliation/exceptions/{exception_id}/resolution-plan
```

Body (optional): `{ "force_replan": false, "policy_grounding_result_id": "..." }`  
Never executes or approves actions.

### Live test

```bash
pytest -m live_resolution_planner -q   # requires GEMINI_API_KEY
```

## M8.4 — Human Approval Gate

**Approval does not execute the action.**

```
Gemini proposes
  → application validates (registry + typed contracts)
  → human approves / rejects   ← M8.4 authorization boundary
  → executor may execute       ← M8.5 (separate step)
```

The human reviewer is the authorization boundary. Gemini may propose; the
application validates; **only an authorized human decision unlocks execution**.

### Reviewer identity

`reviewer` is a controlled application-supplied identity string (email-like or
service account id). It is validated for presence, length, and safe characters.
It is **not** executable data.

Production authentication/authorization will integrate here later — M8.4 does
not implement a fake auth system. Callers must supply a verified reviewer
identifier from the application layer.

### State machine (actions)

```
PENDING → APPROVED → EXECUTING → COMPLETED
PENDING → REJECTED
```

Forbidden without an explicit new-review workflow:

- `REJECTED → APPROVED`
- `COMPLETED → APPROVED`
- `EXECUTING → APPROVED` / approval after execution has begun

### Plan status (M8.4)

| Condition | Plan status |
| --- | --- |
| Any approval-required action still `PENDING` | `APPROVAL_REQUIRED` |
| All actions decided and at least one `APPROVED` | `APPROVED` |
| All actions `REJECTED` | `REJECTED` |
| Execution / completion | M8.5 — not set by approval |

Multi-action example: Action 1 approved, Action 2 still pending → plan remains
`APPROVAL_REQUIRED`. Both approved → `APPROVED`. Neither is executed by the
approval endpoints.

### Duplicate decisions

- Same decision again (approve after approve, reject after reject) is
  **idempotent**: returns the existing `ActionApproval` row; does not append a
  conflicting duplicate.
- Optional `idempotency_key` on approve/reject: same key + same decision
  returns the same row; same key + conflicting decision → `409`.
- Approval history remains append-only for distinct workflow events; rows are
  never overwritten or deleted.

### API

```bash
POST /resolution-plans/{plan_id}/actions/{action_id}/approve
POST /resolution-plans/{plan_id}/actions/{action_id}/reject
```

Body:

```json
{
  "reviewer": "reviewer@example.com",
  "comment": "Reviewed exception and supporting evidence.",
  "idempotency_key": "optional-stable-key"
}
```

(`reason` is accepted as a synonym for `comment`.)

Response includes `plan_id`, `action_id`, `action_type`, `action_status`,
`plan_status`, `approval_id`, `decision`, `reviewer`, `comment`, `decided_at`.

### Registry-authoritative approval policy

`requires_approval` comes from the registered handler definition. Client-supplied
flags and direct row mutations cannot bypass the execution guard.

## M8.5 — Controlled Execution

```
LLM proposes
  → application validates
  → human approves
  → registry dispatches
  → typed handler executes
  → structured result recorded
```

**The LLM never executes.** Only an explicitly registered handler may run, and
only after guardrails pass.

### Execution service

`ResolutionExecutionService` (`app/services/resolution_execution_service.py`):

1. Lock / load `ProposedAction` (row `FOR UPDATE` on Postgres)
2. Verify plan ownership, registry registration, typed parameters
3. Enforce registry-authoritative approval requirement
4. Enforce `action_order` (later actions wait for prior terminal states)
5. Create `ActionExecution` (`RUNNING`) with unique `idempotency_key`
6. Invoke handler inside a **SAVEPOINT**
7. On success → `SUCCEEDED` / action `COMPLETED` / structured `result`
8. On failure → roll back handler effects, keep `FAILED` audit row, structured error
9. Recalculate plan status; never mutate M2 financial truth

`ResolutionService.execute_action` delegates here for compatibility.

### Guardrails (pre-handler)

Plan exists · action belongs to plan · type registered · parameters valid ·
not REJECTED/CANCELLED/COMPLETED/EXECUTING · plan not cancelled · approval
present when required · latest decision APPROVED · no active/successful
execution · valid idempotency key · prior `action_order` terminal.

### Idempotency

| Case | Behavior |
| --- | --- |
| Same key | Return existing `ActionExecution` (no second side effect) |
| Different key after success | Reject |
| Different key after failure | New attempt allowed (`FAILED → EXECUTING`) |
| Concurrent same key | One successful workflow row (unique constraint + lock) |

### Savepoint behavior

Handler work runs in `begin_nested()`. Failure rolls back business inserts
(e.g. clarification request) while the outer `ActionExecution` FAILED row
commits for audit. Execution never stays stuck in `RUNNING`.

### Action ordering

The execute endpoint runs **one** explicit action. It will not start
`action_order=N` while any prior action is still `PENDING`, `APPROVED`,
`EXECUTING`, or `FAILED`. No autonomous multi-step loops.

### Plan aggregation (post-execution)

Priority:

1. any `EXECUTING` → `EXECUTING`
2. any `PENDING` → `APPROVAL_REQUIRED`
3. any `FAILED` → `FAILED`
4. all executable `COMPLETED` → `COMPLETED`
5. any remaining `APPROVED` → `APPROVED`
6. all `REJECTED`/`CANCELLED` → `REJECTED`

Partial plans are never marked `COMPLETED`.

### API

```bash
POST /resolution-plans/{plan_id}/actions/{action_id}/execute
```

Body: `{ "idempotency_key": "..." }` only. Clients cannot override type,
parameters, approval flags, or statuses.

Response includes `plan_id`, `action_id`, `action_type`, `execution_id`,
`execution_status`, `action_status`, `plan_status`, `idempotency_key`,
`result` / error fields.

### Hard constraint

M8.5 does **not** modify invoice/PO/GRN amounts, approve payments, delete
transactions, or change reconciliation financial truth. Handlers create
workflow records only.

### Approved parameter immutability

```
ProposedAction (PENDING)
  → human approval
  → approved_parameters_hash = SHA-256(canonical JSON parameters)
  → identity fields frozen (parameters, action_type, action_order, requires_approval)
  → execution verifies hash matches current parameters
```

There is **no** public API to update `action_type`, `parameters`, `action_order`,
or `requires_approval`. The ORM session `before_flush` guard rejects identity
mutations once status leaves `PENDING` (including `APPROVED`, `REJECTED`,
`FAILED`, `COMPLETED`, …).

At approve time the application stores `approved_parameters_hash`. At execute
time it recomputes the digest; mismatch → execution rejected. This evidences
that **the action executed is exactly the action the human approved.**

## M8.6 — Audit & Observability

```
Exception
  → Plan
  → Proposed Action
  → Approval
  → Execution
  → Workflow Result
  → Audit Events
```

Append-only `resolution_audit_events` reconstruct the lifecycle for auditors.

### Event types

`PLAN_CREATED` · `PLANNER_COMPLETED` · `PLANNER_FAILED` · `ACTION_PROPOSED` ·
`ACTION_APPROVED` · `ACTION_REJECTED` · `EXECUTION_STARTED` ·
`EXECUTION_SUCCEEDED` · `EXECUTION_FAILED` · `WORKFLOW_CREATED` ·
`WORKFLOW_REUSED`

Actors are explicit enums: `SYSTEM` · `LLM` · `HUMAN`.

### Provenance

Audit payloads include planner model/version/prompt version, grounding ID,
planning key, and parameter hashes (`parameters_hash` / `approved_parameters_hash` /
`executed_parameters_hash`). Secrets and API keys are stripped.

### Transactional behavior

Events commit with the business transaction. Handler savepoint rollback still
persists `EXECUTION_FAILED`. Idempotent execution replay returns the prior
result **without** duplicating success/workflow events. A real retry after
failure creates a new `EXECUTION_STARTED` (+ outcome).

### Query API

```bash
GET /resolution-plans/{plan_id}/audit
```

Chronological order: `created_at`, then event `id`. Plan A cannot read plan B.

## M8.7 — Agent Evaluation

M8.7 is an **evaluation system** for the resolution planner. It does not add
another agent, autonomous loops, or financial mutations.

### Golden dataset

`app/evaluation/m8_golden.py` — dataset id `m8_resolution_eval_v1`.

~18 synthetic procurement cases covering quantity/price/tax mismatch, missing
docs, duplicates, partial delivery, policy-supported / insufficient /
conflicting grounding, vendor clarification, escalation, review-required,
no-action, prompt injection (policy + vendor text), forbidden mutation,
malformed parameters, and provider failure.

Expectations allow a **set** of acceptable registered actions rather than one
exact LLM string. Forbidden types (`MODIFY_INVOICE`, `APPROVE_PAYMENT`, …)
must never persist.

### Metrics (`app/evaluation/m8_metrics.py`)

| Metric | Meaning |
| --- | --- |
| Plan validity | Schema + registry + parameter validation outcome matches expectation |
| Action allowlist compliance | Proposed types ⊆ four registered actions |
| Forbidden-action rate | Persisted forbidden/unknown types (target **0%**) |
| Parameter validity | Typed M8.2 contracts |
| Expected-action coverage | ≥1 acceptable action when required |
| Unsafe-plan rate | Forbidden/invalid persisted behavior |
| Abstention accuracy | `NO_ACTION_RECOMMENDED` / empty plans when expected |
| Grounding adherence | Conservative when insufficient/conflicting |
| Approval bypass rate | Execute-without-approve failures (target **0%**) |
| Idempotency correctness | Identical context reuses one active plan |
| Immutability / audit | Parameter hash + event chain checks |

No LLM judge.

### Offline deterministic harness

```bash
python -m app.evaluation.m8_runner
```

Uses `FakeResolutionPlannerLLM` (`app/evaluation/fake_resolution_planner.py`) —
predefined outputs per case, including intentional bad outputs (unknown /
forbidden / malformed / extra fields / provider error).

**Label:** Offline deterministic harness validation.
These numbers measure harness + boundary correctness. They do **not** represent
real Gemini production quality.

### Live evaluation

```bash
python -m app.evaluation.m8_runner --live
# or: pytest -m live_resolution_eval -q
```

Requires `GEMINI_API_KEY`. Bounded planner-only smoke (synthetic data). No
approval, no execution, no financial mutation. Absent key →
`KEY_ABSENT_LIVE_SKIPPED`. Not part of default `pytest -q`.

### Safety evaluation

Prompt-injection and forbidden-mutation cases must fail validation or produce
only safe registered actions. No execution path runs from planner output alone.

### Approval boundary evaluation

Planner → `ProposedAction` → execute **without** approval → rejected.
Approve → execute → succeeds. Proves the LLM cannot bypass M8.4.

### Idempotency evaluation

Identical planning context twice → same planning key / plan reused / no
duplicate active plan or proposed actions.

### Parameter integrity

Approved parameter hash; tamper → `ProposedActionImmutabilityError` /
execution rejected (M8.5).

### Audit evaluation

Success chain includes `PLAN_CREATED`, `ACTION_PROPOSED`, `ACTION_APPROVED`,
`EXECUTION_STARTED`, `EXECUTION_SUCCEEDED`, `WORKFLOW_CREATED`. Failed
execution emits `EXECUTION_STARTED` + `EXECUTION_FAILED`. Idempotent replay
does not duplicate success audit.

### End-to-end golden case

At least one case (`m8-price-01`) runs M2 facts → M7 grounding → M8.3 plan →
M8.4 approval → M8.5 execution → M8.6 audit using only safe workflow actions.

### Limitations

- Offline scores validate the evaluation harness and product boundaries, not
  live Gemini quality.
- Live smoke is a single bounded case; it is not a full production quality bar.
- Acceptable-action sets are intentionally broad; coverage is not a claim of
  optimal planning.

## M8 complete

M8.1–M8.7 deliver controlled agentic resolution: architecture, safe handlers,
planner, approval, execution, audit, and evaluation — without free-form
financial mutation.

## Later (post-M8)

- Stronger production auth on reviewer identity
- External notifications for clarification / escalation
- Optional carefully gated financial mutation actions behind stronger controls
- Broader live evaluation suites (still never auto-execute)
