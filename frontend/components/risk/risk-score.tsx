import { EnumBadge } from "@/components/ui/enum-badge";

export function RiskScore({
  score,
  band,
  signalCount,
  scoreVersion,
  asOf,
}: {
  score: number;
  band: string;
  signalCount: number;
  scoreVersion?: string;
  asOf?: string;
}) {
  const visual = Math.max(0, Math.min(100, score));
  const radius = 58;
  const circumference = 2 * Math.PI * radius;
  const dash = (visual / 100) * circumference;

  return (
    <div className="reveal flex flex-wrap items-center gap-8">
      <svg width="148" height="148" viewBox="0 0 148 148" role="img" aria-label={`Stored risk score ${score}`}>
        <circle cx="74" cy="74" r={radius} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth="2" />
        <circle
          cx="74"
          cy="74"
          r={radius}
          fill="none"
          stroke="currentColor"
          className="text-brand"
          strokeWidth="2"
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          transform="rotate(-90 74 74)"
        />
        <text x="74" y="80" textAnchor="middle" fill="#f4f7f6" fontSize="32" fontWeight="600">
          {score}
        </text>
      </svg>
      <div>
        <p className="text-[11px] font-medium tracking-[0.18em] text-ink-faint uppercase">Stored risk score</p>
        <div className="mt-3">
          <EnumBadge value={band} kind="severity" />
        </div>
        <dl className="mt-4 space-y-1 text-sm text-ink-muted">
          <div>Score version {scoreVersion ?? "not shown here"}</div>
          <div>As of {asOf ?? "not shown here"}</div>
          <div>{signalCount} contributing anomaly signals</div>
        </dl>
        <p className="mt-4 max-w-md text-sm leading-6 text-ink-muted">
          Deterministic risk signal — not a probability of fraud. The ring shows the stored score on
          a 0–100 scale. The number is the stored score.
        </p>
      </div>
    </div>
  );
}
