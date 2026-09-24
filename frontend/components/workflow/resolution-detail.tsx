"use client";

import Link from "next/link";
import { useState } from "react";

import { RecordState } from "@/components/procurement/record-state";
import { resourceError, useResource } from "@/components/procurement/use-resource";
import { ConfirmDialog } from "@/components/workflow/confirm-dialog";
import { EnumBadge } from "@/components/ui/enum-badge";
import {
  approveProposedAction,
  executeProposedAction,
  getResolutionPlan,
  listApprovals,
  listAudit,
  listExecutions,
  rejectProposedAction,
} from "@/lib/api/workflow";
import { formatTimestamp, readableLabel } from "@/lib/labels";
import { actorLabel, approvalAllowed, executionAllowed, redactMetadata } from "@/lib/workflow/presentation";
import type { ProposedAction } from "@/types/workflow";

type DialogKind = "approve" | "reject" | "execute" | null;

function statusNote(status: string): string | null {
  if (status === "REJECTED") {
    return "This plan was rejected. Rejected actions are not executed.";
  }
  if (status === "CANCELLED") {
    return "This plan was cancelled.";
  }
  if (status === "FAILED") {
    return "This plan failed. The failure is shown on the action or execution record.";
  }
  if (status === "NO_ACTION_RECOMMENDED") {
    return "The planner stored no recommended action.";
  }
  return null;
}

export function ResolutionDetail({ id }: { id: string }) {
  const [generation, setGeneration] = useState(0);
  const planState = useResource(`${id}:${generation}`, (signal) => getResolutionPlan(id, signal), "Resolution plan");
  const approvalState = useResource(`${id}:approvals:${generation}`, (signal) => listApprovals(id, signal), "Approvals");
  const executionState = useResource(
    `${id}:executions:${generation}`,
    (signal) => listExecutions(id, signal),
    "Executions",
  );
  const auditState = useResource(`${id}:audit:${generation}`, (signal) => listAudit(id, signal), "Audit trail");
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [action, setAction] = useState<ProposedAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [comment, setComment] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");

  function open(kind: DialogKind, target: ProposedAction) {
    setAction(target);
    setIdempotencyKey(crypto.randomUUID());
    setError(null);
    setDialog(kind);
  }

  async function submit() {
    if (!action || !dialog) {
      return;
    }
    if ((dialog === "approve" || dialog === "reject") && reviewer.trim().length === 0) {
      setError("Enter a reviewer before recording this decision.");
      return;
    }
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      if (dialog === "approve") {
        const result = await approveProposedAction(id, action.id, {
          reviewer,
          comment: comment || undefined,
          idempotency_key: idempotencyKey,
        });
        setNotice(
          `Backend recorded ${result.decision} for ${result.action_type}. Action status is ${result.action_status}. This did not execute the action.`,
        );
      } else if (dialog === "reject") {
        const result = await rejectProposedAction(id, action.id, {
          reviewer,
          comment: comment || undefined,
          idempotency_key: idempotencyKey,
        });
        setNotice(
          `Backend recorded ${result.decision} for ${result.action_type}. Action status is ${result.action_status}.`,
        );
      } else {
        const result = await executeProposedAction(id, action.id, idempotencyKey);
        const failure = result.error_message ? ` ${result.error_message}` : "";
        setNotice(
          `Backend recorded execution ${result.execution_status} for ${result.action_type}. Action status is ${result.action_status}.${failure}`,
        );
      }
      setDialog(null);
      setGeneration((value) => value + 1);
    } catch (caught) {
      setError(resourceError(caught, "Resolution action"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={planState} loadingTitle="Loading resolution plan" empty={null}>
        {(plan) => {
          const note = statusNote(plan.status);
          return (
            <>
              <div>
                <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">
                  AI-proposed resolution plan
                </p>
                <h1 className="mt-1 text-2xl font-semibold">Resolution plan</h1>
                <p className="mt-2 text-sm leading-6 text-ink-muted">
                  A model or system proposed this plan. Human approval is the authorization boundary.
                  The interface does not treat the proposal as a decision to execute.
                </p>
                <div className="mt-3">
                  <EnumBadge value={plan.status} kind="status" />
                </div>
              </div>
              <ol aria-label="Stored resolution status" className="space-y-0">
                {["PROPOSED", "APPROVAL_REQUIRED", "APPROVED", "EXECUTING", "COMPLETED"].map((status) => {
                  const current = plan.status === status;
                  return (
                    <li key={status} className="flex gap-4" aria-current={current ? "step" : undefined}>
                      <span className="flex flex-col items-center">
                        <span className={`mt-1 h-2.5 w-2.5 rounded-full ${current ? "bg-brand" : "border border-white/30"}`} />
                        <span className="w-px flex-1 bg-white/10" aria-hidden="true" />
                      </span>
                      <div className="pb-5">
                        <p className={`text-sm tracking-[0.12em] uppercase ${current ? "text-ink" : "text-ink-faint"}`}>
                          {status.replaceAll("_", " ")}
                        </p>
                        <p className="text-xs text-ink-muted">{current ? "Stored status" : "Not the stored status"}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
              {note ? (
                <p className="rounded-md border border-line bg-canvas p-3 text-sm" role="status">
                  {note}
                </p>
              ) : null}
              {notice ? (
                <p className="rounded-md border border-line bg-surface p-3 text-sm" role="status">
                  {notice}
                </p>
              ) : null}
              {error ? (
                <p className="rounded-md border border-danger bg-danger-soft p-3 text-sm" role="alert">
                  {error}
                </p>
              ) : null}

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Proposal</h2>
                <p className="mt-2 text-sm leading-6">{plan.reasoning_summary || "No reasoning summary was stored."}</p>
                <h3 className="mt-4 text-sm font-semibold">Limitations</h3>
                <p className="mt-1 text-sm leading-6">{plan.limitations || "No limitations text was stored."}</p>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Exception</dt>
                    <dd className="mt-1">
                      <Link className="break-all text-brand underline" href={`/exceptions/${plan.reconciliation_exception_id}`}>
                        {plan.reconciliation_exception_id}
                      </Link>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Proposed by</dt>
                    <dd className="mt-1">{plan.proposed_by ?? "Not stored"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Planner model</dt>
                    <dd className="mt-1">{plan.planner_model ?? "Not stored"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Created</dt>
                    <dd className="mt-1">{formatTimestamp(plan.created_at)}</dd>
                  </div>
                </dl>
              </section>

              <section className="space-y-4">
                <h2 className="text-base font-semibold">Proposed actions</h2>
                {plan.actions.length === 0 ? (
                  <p className="text-sm text-ink-muted">No actions were stored on this plan.</p>
                ) : (
                  plan.actions.map((item) => {
                    const allowApproval = approvalAllowed(item);
                    const allowExecute = executionAllowed(item);
                    return (
                      <article key={item.id} className="rounded-md border border-line bg-surface p-5">
                        <h3 className="text-sm font-semibold">{readableLabel(item.action_type)}</h3>
                        <p className="text-xs text-ink-muted">{item.action_type}</p>
                        <div className="mt-2">
                          <EnumBadge value={item.status} kind="status" />
                        </div>
                        <p className="mt-3 text-sm leading-6">{item.rationale || "No rationale was stored."}</p>
                        <p className="mt-2 text-sm">
                          {item.requires_approval
                            ? item.status === "APPROVED"
                              ? "Human approval is recorded. Execution still requires an explicit action."
                              : item.status === "REJECTED"
                                ? "Human approval was refused. Execution is not offered."
                                : "Human approval required before execution."
                            : "The stored action does not require a separate approval flag."}
                        </p>
                        <h4 className="mt-3 text-sm font-semibold">Parameters</h4>
                        <pre className="mt-1 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
                          {JSON.stringify(item.parameters, null, 2)}
                        </pre>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {allowApproval ? (
                            <>
                              <button type="button" className="min-h-10 rounded-lg bg-brand px-3 py-2 text-sm text-on-brand" onClick={() => open("approve", item)}>
                                Approve this proposed action
                              </button>
                              <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => open("reject", item)}>
                                Reject this proposed action
                              </button>
                            </>
                          ) : null}
                          {allowExecute ? (
                            <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => open("execute", item)}>
                              Execute approved action
                            </button>
                          ) : null}
                        </div>
                      </article>
                    );
                  })
                )}
              </section>

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Approval</h2>
                {approvalState.kind === "loading" ? <p className="mt-2 text-sm">Loading approvals.</p> : null}
                {approvalState.kind === "error" ? (
                  <p className="mt-2 text-sm" role="alert">
                    {approvalState.message}
                  </p>
                ) : null}
                {approvalState.kind === "ready" && approvalState.data.items.length === 0 ? (
                  <p className="mt-2 text-sm text-ink-muted">No human approval decision is stored.</p>
                ) : null}
                {approvalState.kind === "ready" ? (
                  <ul className="mt-3 space-y-3">
                    {approvalState.data.items.map((row) => (
                      <li key={row.id} className="border-t border-line pt-3 text-sm">
                        <EnumBadge value={row.decision} kind="status" />
                        <p className="mt-2">Reviewer {row.reviewer}</p>
                        <p>{row.reason ?? "No reason stored"}</p>
                        <p className="text-ink-muted">{formatTimestamp(row.decided_at)}</p>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Execution</h2>
                {executionState.kind === "loading" ? <p className="mt-2 text-sm">Loading executions.</p> : null}
                {executionState.kind === "error" ? (
                  <p className="mt-2 text-sm" role="alert">
                    {executionState.message}
                  </p>
                ) : null}
                {executionState.kind === "ready" && executionState.data.items.length === 0 ? (
                  <p className="mt-2 text-sm text-ink-muted">No execution has been recorded.</p>
                ) : null}
                {executionState.kind === "ready"
                  ? executionState.data.items.map((row) => (
                      <article key={row.id} className="mt-3 border-t border-line pt-3 text-sm">
                        <EnumBadge value={row.execution_status} kind="status" />
                        <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                          <div>
                            <dt className="text-xs uppercase text-ink-muted">Started</dt>
                            <dd>{row.started_at ? formatTimestamp(row.started_at) : "Not started"}</dd>
                          </div>
                          <div>
                            <dt className="text-xs uppercase text-ink-muted">Completed</dt>
                            <dd>{row.completed_at ? formatTimestamp(row.completed_at) : "Not completed"}</dd>
                          </div>
                        </dl>
                        {row.error_message ? (
                          <p className="mt-2" role="alert">
                            Execution failed: {row.error_code ? `${row.error_code}. ` : ""}
                            {row.error_message}
                          </p>
                        ) : null}
                        <h3 className="mt-2 text-sm font-semibold">Result</h3>
                        <pre className="mt-1 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
                          {JSON.stringify(redactMetadata(row.result ?? {}), null, 2)}
                        </pre>
                      </article>
                    ))
                  : null}
              </section>

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Audit trail</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  SYSTEM, LLM, and HUMAN are actor labels. An LLM event is not authorization.
                </p>
                {auditState.kind === "loading" ? <p className="mt-2 text-sm">Loading audit events.</p> : null}
                {auditState.kind === "error" ? (
                  <p className="mt-2 text-sm" role="alert">
                    {auditState.message}
                  </p>
                ) : null}
                {auditState.kind === "ready" && auditState.data.events.length === 0 ? (
                  <p className="mt-2 text-sm text-ink-muted">No audit events were stored.</p>
                ) : null}
                {auditState.kind === "ready" ? (
                  <ol className="mt-3 space-y-3">
                    {[...auditState.data.events]
                      .sort((left, right) => left.created_at.localeCompare(right.created_at))
                      .map((event) => (
                        <li key={event.id} className="border-t border-line pt-3 text-sm">
                          <p className="font-medium">{readableLabel(event.event_type)}</p>
                          <p>
                            Actor type {actorLabel(event.actor_type)}
                            {event.actor_id ? ` · ${event.actor_id}` : ""}
                          </p>
                          <p className="text-ink-muted">{formatTimestamp(event.created_at)}</p>
                          <pre className="mt-2 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
                            {JSON.stringify(redactMetadata(event.data), null, 2)}
                          </pre>
                        </li>
                      ))}
                  </ol>
                ) : null}
              </section>

              <ConfirmDialog
                open={dialog === "approve" && action !== null}
                title="Approve this proposed action?"
                description={
                  action
                    ? `Action type: ${action.action_type}. This records human approval only. It does not execute the action.`
                    : ""
                }
                confirmLabel="Approve proposed action"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() => void submit()}
              >
                <ReviewerFields reviewer={reviewer} comment={comment} onReviewer={setReviewer} onComment={setComment} required />
              </ConfirmDialog>
              <ConfirmDialog
                open={dialog === "reject" && action !== null}
                title="Reject this proposed action?"
                description={
                  action
                    ? `Action type: ${action.action_type}. A rejected action is not executed.`
                    : ""
                }
                confirmLabel="Reject proposed action"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() => void submit()}
              >
                <ReviewerFields reviewer={reviewer} comment={comment} onReviewer={setReviewer} onComment={setComment} required />
              </ConfirmDialog>
              <ConfirmDialog
                open={dialog === "execute" && action !== null}
                title="Execute this approved action?"
                description={
                  action
                    ? `Action type: ${action.action_type}. Approval state: ${action.status}. The backend will use the stored parameters below. This screen does not change them.`
                    : ""
                }
                confirmLabel="Execute approved action"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() => void submit()}
              >
                {action ? (
                  <pre className="mt-3 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
                    {JSON.stringify(action.parameters, null, 2)}
                  </pre>
                ) : null}
                {action?.rationale ? <p className="mt-2 text-sm">Stored rationale: {action.rationale}</p> : null}
              </ConfirmDialog>
            </>
          );
        }}
      </RecordState>
    </div>
  );
}

function ReviewerFields({
  reviewer,
  comment,
  onReviewer,
  onComment,
  required,
}: {
  reviewer: string;
  comment: string;
  onReviewer: (value: string) => void;
  onComment: (value: string) => void;
  required?: boolean;
}) {
  return (
    <div className="mt-4 grid gap-3">
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Reviewer
        <input
          required={required}
          className="rounded-md border border-line px-2 py-2 text-sm text-ink"
          value={reviewer}
          onChange={(event) => onReviewer(event.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Reason
        <textarea
          className="rounded-md border border-line px-2 py-2 text-sm text-ink"
          value={comment}
          onChange={(event) => onComment(event.target.value)}
        />
      </label>
    </div>
  );
}
