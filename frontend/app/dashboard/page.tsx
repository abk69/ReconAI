import { SystemStatus } from "@/components/dashboard/system-status";
import { PlaceholderSection } from "@/components/ui/placeholder-section";
import { RiskBandBadge } from "@/components/ui/status-badge";
import type { RiskBand } from "@/types/domain";

const previewBands: RiskBand[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Dashboard</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
          ReconAI reconciles purchase orders, goods receipts, and invoices with deterministic
          financial checks. Later screens will separate those facts from anomaly and risk signals,
          policy-grounded explanations, and AI-assisted recommendations. This page does not show
          live financial totals.
        </p>
      </div>

      <SystemStatus />

      <section
        aria-labelledby="band-preview-heading"
        className="rounded-md border border-line bg-surface p-5 shadow-card"
      >
        <h2 id="band-preview-heading" className="text-base font-semibold text-ink">
          Risk band labels
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Preview of the label style only. These are not scores for any vendor, invoice, or
          purchase order.
        </p>
        <ul className="mt-4 flex flex-wrap gap-2">
          {previewBands.map((band) => (
            <li key={band}>
              <RiskBandBadge band={band} />
            </li>
          ))}
        </ul>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <PlaceholderSection
          title="Reconciliation Overview"
          description="Match outcomes from the deterministic reconciliation engine will appear here. No counts or amounts are shown until that view is connected."
        />
        <PlaceholderSection
          title="Open Exceptions"
          description="Exceptions awaiting human review will be listed here. This milestone does not load the review queue."
        />
        <PlaceholderSection
          title="Risk Intelligence"
          description="Anomaly signals and versioned risk bands will be summarized here. Scores are risk signals, not fraud determinations, and none are displayed yet."
        />
        <PlaceholderSection
          title="Document Processing"
          description="Intake and extraction status will appear here after the document screens are built. No documents are loaded on this page."
        />
      </div>

      <PlaceholderSection
        title="Recent Activity"
        description="Audit and workflow events will appear here in a later milestone. The activity feed is empty because it has not been connected."
      />
    </div>
  );
}
