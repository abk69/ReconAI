import type { ReactNode } from "react";
import Link from "next/link";

import { CountBars } from "@/components/dashboard/count-bars";
import { EmptyState } from "@/components/ui/state";
import { EnumBadge } from "@/components/ui/enum-badge";
import { RiskBandBadge } from "@/components/ui/status-badge";
import { formatTimestamp, readableLabel } from "@/lib/labels";
import type { DashboardSummary } from "@/types/dashboard";
import type { RiskBand } from "@/types/domain";

function isRiskBand(value: string): value is RiskBand {
  return value === "LOW" || value === "MEDIUM" || value === "HIGH" || value === "CRITICAL";
}

function Panel({
  id,
  title,
  note,
  children,
}: {
  id: string;
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 id={id} className="text-base font-semibold text-ink">
        {title}
      </h2>
      {note ? <p className="mt-1 text-sm leading-6 text-ink-muted">{note}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function KpiRow({ summary }: { summary: DashboardSummary }) {
  const cards = [
    {
      label: "Documents",
      value: summary.documents.total,
      detail: "Persisted document records",
    },
    {
      label: "Open exceptions",
      value: summary.open_exception_count,
      detail: "Reconciliation exceptions with status OPEN",
    },
    {
      label: "High / critical risk",
      value: summary.high_or_critical_risk_count,
      detail: "Latest persisted risk profile per entity",
    },
    {
      label: "Pending review",
      value: summary.pending_review_count,
      detail: "Review tasks with status PENDING",
    },
  ];

  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <li key={card.label} className="rounded-md border border-line bg-surface px-4 py-4 shadow-card">
          <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">{card.label}</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-ink">{card.value}</p>
          <p className="mt-1 text-xs leading-5 text-ink-muted">{card.detail}</p>
        </li>
      ))}
    </ul>
  );
}

export function ReconciliationPanel({ summary }: { summary: DashboardSummary }) {
  return (
    <Panel id="reconciliation-heading" title="Reconciliation overview" note={summary.reconciliation_note}>
      <p className="mb-3 text-sm text-ink">
        Open {summary.open_exception_count}
        <span className="mx-2 text-ink-muted">·</span>
        In review {summary.in_review_exception_count}
      </p>
      <CountBars
        counts={summary.reconciliation_exceptions}
        emptyLabel="No reconciliation exceptions have been recorded."
      />
    </Panel>
  );
}

export function ExceptionsPanel({ summary }: { summary: DashboardSummary }) {
  return (
    <Panel
      id="exceptions-heading"
      title="Open exceptions"
      note="OPEN and IN_REVIEW exceptions, newest first. Detail screens are not available yet."
    >
      {summary.open_exceptions.length === 0 ? (
        <EmptyState
          title="No open exceptions"
          description="No reconciliation exceptions have been recorded with status OPEN or IN_REVIEW."
        />
      ) : (
        <ul className="divide-y divide-line">
          {summary.open_exceptions.map((item) => (
            <li key={item.id} className="py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <EnumBadge value={item.exception_type} kind="status" />
                <EnumBadge value={item.severity} kind="severity" />
                <EnumBadge value={item.status} kind="status" />
              </div>
              <p className="mt-2 text-sm text-ink">{item.message}</p>
              <p className="mt-1 text-xs text-ink-muted">
                {item.invoice_number ? `Invoice ${item.invoice_number}` : "No invoice reference"}
                {item.po_number ? ` · PO ${item.po_number}` : ""}
                {item.grn_number ? ` · GRN ${item.grn_number}` : ""}
                {" · "}
                {formatTimestamp(item.created_at)}
              </p>
              <Link href="/exceptions" className="mt-1 inline-block text-sm text-brand underline">
                Exceptions section
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function RiskPanel({ summary }: { summary: DashboardSummary }) {
  return (
    <Panel id="risk-heading" title="Risk intelligence" note={summary.risk_note}>
      <h3 className="text-sm font-medium text-ink">Latest risk profiles by band</h3>
      <div className="mt-2">
        <CountBars
          counts={summary.risk_profiles}
          emptyLabel="No risk profiles have been persisted."
        />
      </div>
      <h3 className="mt-5 text-sm font-medium text-ink">Anomaly signals by severity</h3>
      <p className="mt-1 text-xs text-ink-muted">
        Persisted anomaly signals. These are not risk scores and not fraud determinations.
      </p>
      <div className="mt-2">
        <CountBars
          counts={summary.anomaly_signals}
          emptyLabel="No anomaly signals have been recorded."
        />
      </div>
      {summary.latest_risk_profiles.length === 0 ? null : (
        <ul className="mt-5 divide-y divide-line">
          {summary.latest_risk_profiles.map((profile) => (
            <li key={profile.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="text-sm text-ink">
                  {readableLabel(profile.entity_type)} · score {profile.score}
                </p>
                <p className="text-xs text-ink-muted">
                  as of {profile.as_of} · {profile.signal_count} signal
                  {profile.signal_count === 1 ? "" : "s"} · {profile.score_version}
                </p>
              </div>
              {isRiskBand(profile.risk_band) ? <RiskBandBadge band={profile.risk_band} /> : profile.risk_band}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function DocumentsPanel({ summary }: { summary: DashboardSummary }) {
  return (
    <Panel id="documents-heading" title="Document processing" note={summary.document_note}>
      <CountBars
        counts={summary.documents}
        emptyLabel="No documents have been recorded."
      />
    </Panel>
  );
}

export function ReviewPanel({ summary }: { summary: DashboardSummary }) {
  return (
    <Panel id="review-heading" title="Human review" note={summary.review_note}>
      <CountBars
        counts={summary.review_tasks}
        emptyLabel="No review tasks have been recorded."
      />
      {summary.pending_reviews.length === 0 ? null : (
        <ul className="mt-4 divide-y divide-line">
          {summary.pending_reviews.map((task) => (
            <li key={task.id} className="py-3">
              <div className="flex flex-wrap items-center gap-2">
                <EnumBadge value={task.status} kind="status" />
                <EnumBadge value={task.priority} kind="severity" />
              </div>
              <p className="mt-2 text-sm text-ink">{task.document_filename}</p>
              <p className="mt-1 text-xs text-ink-muted">
                {task.reason ?? "No reason recorded"} · {formatTimestamp(task.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function ActivityPanel({ summary }: { summary: DashboardSummary }) {
  return (
    <Panel
      id="activity-heading"
      title="Recent activity"
      note="Newest persisted workflow records. This is not a complete audit log."
    >
      {summary.recent_activity.length === 0 ? (
        <EmptyState
          title="No activity recorded"
          description="Activity appears when documents, exceptions, reviews, anomaly signals, risk profiles, or resolution audit events are stored."
        />
      ) : (
        <ul className="divide-y divide-line">
          {summary.recent_activity.map((item) => (
            <li key={`${item.kind}-${item.record_id}`} className="py-3 first:pt-0">
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">
                {readableLabel(item.kind)}
              </p>
              <p className="mt-1 text-sm text-ink">{item.title}</p>
              <p className="mt-1 text-sm text-ink-muted">{item.detail}</p>
              <p className="mt-1 text-xs text-ink-muted">{formatTimestamp(item.occurred_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
