import type { ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle, ClipboardCheck, FileText, Shield } from "lucide-react";

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
    <section aria-labelledby={id} className="reveal border-t border-white/8 pt-8">
      <h2 id={id} className="text-sm font-medium tracking-[0.16em] text-ink-faint uppercase">
        {title}
      </h2>
      {note ? <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">{note}</p> : null}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function KpiRow({ summary }: { summary: DashboardSummary }) {
  const cards = [
    {
      label: "Documents",
      value: summary.documents.total,
      detail: "Persisted document records",
      icon: FileText,
    },
    {
      label: "Open exceptions",
      value: summary.open_exception_count,
      detail: "Reconciliation exceptions with status OPEN",
      icon: AlertTriangle,
    },
    {
      label: "High / critical risk",
      value: summary.high_or_critical_risk_count,
      detail: "Latest persisted risk profile per entity",
      icon: Shield,
    },
    {
      label: "Pending review",
      value: summary.pending_review_count,
      detail: "Review tasks with status PENDING",
      icon: ClipboardCheck,
    },
  ];

  const [primary, ...rest] = cards;
  const PrimaryIcon = primary.icon;
  return (
    <div className="reveal grid gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:items-end">
      <div>
        <p className="flex items-center gap-2 text-[11px] font-medium tracking-[0.16em] text-ink-faint uppercase">
          <PrimaryIcon aria-hidden="true" size={14} className="text-brand" />
          {primary.label}
        </p>
        <p className="mt-3 text-7xl font-semibold tracking-tight tabular-nums text-ink">
          {String(primary.value).padStart(2, "0")}
        </p>
        <p className="mt-2 max-w-sm text-sm leading-6 text-ink-muted">{primary.detail}</p>
      </div>
      <ul className="divide-y divide-white/8">
        {rest.map((card) => (
          <li key={card.label} className="flex items-baseline justify-between gap-4 py-3">
            <span className="text-[11px] font-medium tracking-[0.14em] text-ink-faint uppercase">{card.label}</span>
            <span className="text-2xl font-semibold tabular-nums text-ink">{String(card.value).padStart(2, "0")}</span>
          </li>
        ))}
      </ul>
    </div>
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
      note="OPEN and IN_REVIEW exceptions, newest first."
    >
      {summary.open_exceptions.length === 0 ? (
        <EmptyState
          title="No open exceptions"
          description="No reconciliation exceptions have been recorded with status OPEN or IN_REVIEW."
        />
      ) : (
        <ul>
          {summary.open_exceptions.map((item) => (
            <li key={item.id} className="border-b border-white/8 py-5">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <Link className="text-base font-medium text-ink" href={`/exceptions/${item.id}`}>
                  {readableLabel(item.exception_type)}
                </Link>
                <EnumBadge value={item.severity} kind="severity" />
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">{item.message}</p>
              <p className="mt-2 text-xs text-ink-muted">
                <EnumBadge value={item.status} kind="status" />
                <span className="ml-2">
                  {item.invoice_number ? `Invoice ${item.invoice_number}` : "No invoice reference"}
                  {item.po_number ? ` · PO ${item.po_number}` : ""}
                  {item.grn_number ? ` · GRN ${item.grn_number}` : ""}
                  {" · "}
                  {formatTimestamp(item.created_at)}
                </span>
              </p>
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
                  as of {profile.as_of} · {profile.signal_count}{" "}
                  {profile.signal_count === 1 ? "signal" : "signals"} · {profile.score_version}
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
