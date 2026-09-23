"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RecordState } from "@/components/procurement/record-state";
import { resourceError, useResource } from "@/components/procurement/use-resource";
import { ConfirmDialog } from "@/components/workflow/confirm-dialog";
import { EnumBadge } from "@/components/ui/enum-badge";
import {
  approveReviewTask,
  correctReviewTask,
  getReviewTask,
  promoteReviewTask,
  rejectReviewTask,
} from "@/lib/api/workflow";
import { formatTimestamp, readableLabel } from "@/lib/labels";
import {
  correctionFields,
  displayValue,
  promotedHref,
  type CorrectionField,
} from "@/lib/workflow/presentation";
type DialogKind = "approve" | "reject" | "promote" | "correct" | null;

function scalarEntries(candidate: Record<string, unknown> | null): [string, unknown][] {
  if (!candidate) {
    return [];
  }
  return Object.entries(candidate).filter(([key, value]) => key !== "lines" && value !== undefined);
}

function lineRows(candidate: Record<string, unknown> | null): Record<string, unknown>[] {
  const lines = candidate?.lines;
  if (!Array.isArray(lines)) {
    return [];
  }
  return lines.filter((line): line is Record<string, unknown> => Boolean(line) && typeof line === "object");
}

function ValueTable({
  title,
  caption,
  candidate,
}: {
  title: string;
  caption: string;
  candidate: Record<string, unknown> | null;
}) {
  const fields = scalarEntries(candidate);
  const lines = lineRows(candidate);
  return (
    <section className="rounded-md border border-line bg-surface p-5">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-ink-muted">{caption}</p>
      {fields.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">No candidate fields were stored.</p>
      ) : (
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          {fields.map(([key, value]) => (
            <div key={key} className="min-w-0">
              <dt className="text-xs uppercase text-ink-muted">{key}</dt>
              <dd className="mt-1 break-words text-sm">{displayValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {lines.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <caption className="sr-only">Line items for {title}</caption>
            <thead>
              <tr>
                {Object.keys(lines[0]).map((key) => (
                  <th key={key} scope="col" className="px-2 py-1 text-xs uppercase text-ink-muted">
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => (
                <tr key={index} className="border-t border-line">
                  {Object.keys(lines[0]).map((key) => (
                    <td key={key} className="px-2 py-1 align-top">
                      {displayValue(line[key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

export function ReviewDetail({ id }: { id: string }) {
  const [generation, setGeneration] = useState(0);
  const state = useResource(`${id}:${generation}`, (signal) => getReviewTask(id, signal), "Review task");
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [fields, setFields] = useState<CorrectionField[]>([]);

  const task = state.kind === "ready" ? state.data : null;

  useEffect(() => {
    if (!task) {
      return;
    }
    const source = task.reviewed_candidate ?? task.original_candidate;
    const nextFields = correctionFields(source);
    const nextDrafts: Record<string, string> = {};
    for (const field of nextFields) {
      nextDrafts[field.path] = field.value;
    }
    setFields(nextFields);
    setDrafts(nextDrafts);
  }, [task]);

  async function run(action: () => Promise<{ status: string }>, success: (status: string) => string) {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const result = await action();
      setNotice(success(result.status));
      setDialog(null);
      setGeneration((value) => value + 1);
    } catch (caught) {
      setError(resourceError(caught, "Review action"));
    } finally {
      setBusy(false);
    }
  }

  function changedCorrections() {
    return fields
      .filter((field) => drafts[field.path] !== field.value)
      .map((field) => ({ field_path: field.path, corrected_value: drafts[field.path] ?? "" }));
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={state} loadingTitle="Loading review task" empty={null}>
        {(item) => {
          const open = item.status === "PENDING" || item.status === "IN_REVIEW";
          const canApprove = open || item.status === "CORRECTED";
          const canCorrect = open;
          const canReject = open;
          const canPromote =
            (item.status === "APPROVED" || item.status === "CORRECTED") && !item.promoted_entity_id;
          const href = promotedHref(item.promoted_entity_type, item.promoted_entity_id);
          const changes = changedCorrections();
          return (
            <>
              <div>
                <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Human review</p>
                <h1 className="mt-1 text-2xl font-semibold">Extraction review</h1>
                <p className="mt-2 text-sm leading-6 text-ink-muted">
                  Extracted values stay visible beside any reviewed correction. Promoted procurement
                  data is authoritative only after the backend records a promotion.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <EnumBadge value={item.status} kind="status" />
                  <EnumBadge value={item.priority} kind="severity" />
                </div>
              </div>

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
              {item.status === "REJECTED" ? (
                <p className="rounded-md border border-danger bg-danger-soft p-3 text-sm" role="status">
                  This review was rejected. The task cannot be approved from this state.
                </p>
              ) : null}

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Source document</h2>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">File</dt>
                    <dd className="mt-1">
                      <Link className="text-brand underline" href={`/documents/${item.document_id}`}>
                        {item.original_filename ?? item.document_id}
                      </Link>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Detected type</dt>
                    <dd className="mt-1">{item.detected_type ?? "Not detected"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Document type</dt>
                    <dd className="mt-1">{item.document_type ?? "Not stored"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Document status</dt>
                    <dd className="mt-1">{item.document_status ?? "Not stored"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Assigned reviewer</dt>
                    <dd className="mt-1">{item.assigned_to ?? "Unassigned"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Created</dt>
                    <dd className="mt-1">{formatTimestamp(item.created_at)}</dd>
                  </div>
                </dl>
              </section>

              <ValueTable
                title="Extracted value"
                caption="Original extraction candidate. This is not a reviewed or promoted value."
                candidate={item.original_candidate}
              />
              <ValueTable
                title="Reviewed or corrected value"
                caption={
                  item.reviewed_candidate
                    ? "Candidate after recorded human corrections."
                    : "No reviewed candidate is stored yet."
                }
                candidate={item.reviewed_candidate}
              />

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Authoritative promoted data</h2>
                {item.promoted_entity_id ? (
                  <p className="mt-2 text-sm leading-6">
                    Promoted as {item.promoted_entity_type ?? "a procurement record"} at{" "}
                    {item.promoted_at ? formatTimestamp(item.promoted_at) : "an unstored time"}.{" "}
                    {href ? (
                      <Link className="text-brand underline" href={href}>
                        Open the promoted record
                      </Link>
                    ) : (
                      "No workspace link is available for this entity type."
                    )}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-ink-muted">
                    Nothing has been promoted. Extracted and reviewed values are not authoritative
                    procurement records.
                  </p>
                )}
              </section>

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Validation findings</h2>
                <p className="mt-1 text-sm text-ink-muted">
                  Stored extraction evidence. Confidence is shown only when the backend stored it.
                </p>
                {item.evidence.length === 0 ? (
                  <p className="mt-3 text-sm text-ink-muted">No extraction evidence was stored.</p>
                ) : (
                  <ul className="mt-3 space-y-3">
                    {item.evidence.map((entry, index) => (
                      <li key={index} className="overflow-x-auto rounded-md bg-canvas p-3 text-sm">
                        <EvidenceEntry entry={entry} />
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {canCorrect ? (
                <form
                  className="rounded-md border border-line bg-surface p-5"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (changes.length === 0) {
                      setError("Change at least one stored field before submitting a correction.");
                      return;
                    }
                    setError(null);
                    setDialog("correct");
                  }}
                >
                  <h2 className="text-base font-semibold">Correction</h2>
                  <p className="mt-1 text-sm text-ink-muted">
                    Fields come from the stored candidate. The backend validates the submitted values.
                  </p>
                  {fields.length === 0 ? (
                    <p className="mt-3 text-sm text-ink-muted">This candidate has no editable fields.</p>
                  ) : (
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      {fields.map((field) => (
                        <label key={field.path} className="flex flex-col gap-1 text-xs text-ink-muted">
                          {field.label}
                          <input
                            className="rounded-md border border-line px-2 py-2 text-sm text-ink"
                            value={drafts[field.path] ?? ""}
                            onChange={(event) =>
                              setDrafts((current) => ({ ...current, [field.path]: event.target.value }))
                            }
                          />
                        </label>
                      ))}
                    </div>
                  )}
                  <button
                    type="submit"
                    className="mt-4 rounded-md border border-line px-3 py-2 text-sm"
                    disabled={fields.length === 0 || busy}
                  >
                    Review correction
                  </button>
                </form>
              ) : null}

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Review actions</h2>
                <div className="mt-3 flex flex-wrap gap-2">
                  {canApprove ? (
                    <button type="button" className="rounded-md bg-brand px-3 py-2 text-sm text-white" onClick={() => setDialog("approve")}>
                      Approve extraction
                    </button>
                  ) : null}
                  {canReject ? (
                    <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => setDialog("reject")}>
                      Reject extraction
                    </button>
                  ) : null}
                  {canPromote ? (
                    <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => setDialog("promote")}>
                      Promote to procurement record
                    </button>
                  ) : null}
                  {!canApprove && !canReject && !canPromote ? (
                    <p className="text-sm text-ink-muted">No further review actions are available for this status.</p>
                  ) : null}
                </div>
              </section>

              <section className="rounded-md border border-line bg-surface p-5">
                <h2 className="text-base font-semibold">Review decision history</h2>
                <p className="mt-1 text-sm text-ink-muted">Append-only. Historical decisions cannot be edited here.</p>
                {item.decisions.length === 0 ? (
                  <p className="mt-3 text-sm text-ink-muted">No decisions have been recorded.</p>
                ) : (
                  <ol className="mt-3 space-y-3">
                    {[...item.decisions]
                      .sort((left, right) => left.created_at.localeCompare(right.created_at))
                      .map((decision) => (
                        <li key={decision.id} className="border-t border-line pt-3 text-sm">
                          <p className="font-medium">{readableLabel(decision.action)}</p>
                          <p>{decision.reviewer ?? "Reviewer not stored"}</p>
                          <p>{decision.reason ?? "No comment stored"}</p>
                          {decision.field_path ? (
                            <p>
                              {decision.field_path}: {displayValue(decision.original_value)} →{" "}
                              {displayValue(decision.corrected_value)}
                            </p>
                          ) : null}
                          <p className="text-ink-muted">{formatTimestamp(decision.created_at)}</p>
                        </li>
                      ))}
                  </ol>
                )}
              </section>

              <ConfirmDialog
                open={dialog === "approve"}
                title="Approve this extraction?"
                description="This records a human approval of the current candidate. It does not promote a procurement record and does not execute a resolution action."
                confirmLabel="Approve extraction"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() =>
                  void run(
                    () => approveReviewTask(item.id, { reviewer: reviewer || undefined, reason: reason || undefined }),
                    (status) => `Backend recorded review status ${status}.`,
                  )
                }
              >
                <IdentityFields reviewer={reviewer} reason={reason} onReviewer={setReviewer} onReason={setReason} />
              </ConfirmDialog>
              <ConfirmDialog
                open={dialog === "reject"}
                title="Reject this extraction review?"
                description="This records a rejection. A rejected task cannot be approved afterward."
                confirmLabel="Reject extraction"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() =>
                  void run(
                    () => rejectReviewTask(item.id, { reviewer: reviewer || undefined, reason: reason || undefined }),
                    (status) => `Backend recorded review status ${status}.`,
                  )
                }
              >
                <IdentityFields reviewer={reviewer} reason={reason} onReviewer={setReviewer} onReason={setReason} />
              </ConfirmDialog>
              <ConfirmDialog
                open={dialog === "promote"}
                title="Promote this reviewed extraction?"
                description="This asks the backend to create the authoritative purchase order, goods receipt, or invoice from the reviewed candidate."
                confirmLabel="Promote extraction"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() =>
                  void run(
                    () => promoteReviewTask(item.id),
                    (status) => `Backend recorded promotion. Review status is ${status}.`,
                  )
                }
              />
              <ConfirmDialog
                open={dialog === "correct"}
                title="Submit these field corrections?"
                description={
                  changes.length === 0
                    ? "No fields differ from the stored candidate."
                    : `Fields: ${changes.map((item) => item.field_path).join(", ")}. The backend will validate each value.`
                }
                confirmLabel="Submit corrections"
                busy={busy}
                onCancel={() => setDialog(null)}
                onConfirm={() =>
                  void run(
                    () =>
                      correctReviewTask(item.id, {
                        reviewer: reviewer || undefined,
                        reason: reason || undefined,
                        corrections: changes,
                      }),
                    (status) => `Backend recorded review status ${status}.`,
                  )
                }
              >
                <IdentityFields reviewer={reviewer} reason={reason} onReviewer={setReviewer} onReason={setReason} />
              </ConfirmDialog>
            </>
          );
        }}
      </RecordState>
    </div>
  );
}

function IdentityFields({
  reviewer,
  reason,
  onReviewer,
  onReason,
}: {
  reviewer: string;
  reason: string;
  onReviewer: (value: string) => void;
  onReason: (value: string) => void;
}) {
  return (
    <div className="mt-4 grid gap-3">
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Reviewer
        <input
          className="rounded-md border border-line px-2 py-2 text-sm text-ink"
          value={reviewer}
          onChange={(event) => onReviewer(event.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Comment
        <textarea
          className="rounded-md border border-line px-2 py-2 text-sm text-ink"
          value={reason}
          onChange={(event) => onReason(event.target.value)}
        />
      </label>
    </div>
  );
}

function EvidenceEntry({ entry }: { entry: unknown }) {
  if (!entry || typeof entry !== "object") {
    return <p>{displayValue(entry)}</p>;
  }
  const record = entry as Record<string, unknown>;
  const keys = Object.keys(record);
  return (
    <dl className="grid gap-2 sm:grid-cols-2">
      {keys.map((key) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs uppercase text-ink-muted">{key}</dt>
          <dd className="mt-1 break-words">{displayValue(record[key])}</dd>
        </div>
      ))}
    </dl>
  );
}
