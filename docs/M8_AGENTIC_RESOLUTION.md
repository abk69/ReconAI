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

## Later milestones (not M8.2)

- LLM agent that produces ResolutionPlans
- Gemini tool calling bound to the ActionRegistry
- External notifications for clarification / escalation
- Optional carefully gated financial mutation actions behind stronger controls
