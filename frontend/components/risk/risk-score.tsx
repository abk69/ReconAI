import { EnumBadge } from "@/components/ui/enum-badge";

export function RiskScore({
  score,
  band,
  signalCount,
}: {
  score: number;
  band: string;
  signalCount: number;
}) {
  return (
    <div className="rounded-md border border-line bg-surface p-5">
      <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Risk score</p>
      <p className="mt-1 text-4xl font-semibold tabular-nums text-ink">{score}</p>
      <p className="mt-2 text-sm text-ink">Risk score: {score}</p>
      <div className="mt-2">
        <EnumBadge value={band} kind="severity" />
      </div>
      <p className="mt-2 text-sm text-ink">{signalCount} contributing anomaly signals</p>
      <p className="mt-3 text-sm leading-6 text-ink-muted">
        Risk scores are deterministic aggregations of anomaly signals. They are not fraud
        probabilities.
      </p>
    </div>
  );
}
