import type { CountMap } from "@/types/dashboard";

import { readableLabel } from "@/lib/labels";

export function CountBars({ counts, emptyLabel }: { counts: CountMap; emptyLabel: string }) {
  const entries = Object.entries(counts.counts);
  const max = Math.max(0, ...entries.map(([, count]) => count));
  if (counts.total === 0) {
    return <p className="text-sm text-ink-muted">{emptyLabel}</p>;
  }

  return (
    <ul className="space-y-3">
      {entries.map(([key, count]) => {
        const width = max === 0 ? 0 : Math.round((count / max) * 100);
        return (
          <li key={key}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm text-ink">
                {key}
                <span className="ml-2 text-[11px] tracking-wide text-ink-faint uppercase">{readableLabel(key)}</span>
              </span>
              <span className="text-sm font-medium tabular-nums text-ink">{count}</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/5" aria-hidden="true">
              <div className="h-1.5 rounded-full bg-brand/80" style={{ width: `${width}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
