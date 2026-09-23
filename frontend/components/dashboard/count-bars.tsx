import type { CountMap } from "@/types/dashboard";

import { readableLabel } from "@/lib/labels";

export function CountBars({ counts, emptyLabel }: { counts: CountMap; emptyLabel: string }) {
  const entries = Object.entries(counts.counts);
  const max = Math.max(0, ...entries.map(([, count]) => count));
  if (counts.total === 0) {
    return <p className="text-sm text-ink-muted">{emptyLabel}</p>;
  }

  return (
    <ul className="space-y-2">
      {entries.map(([key, count]) => {
        const width = max === 0 ? 0 : Math.round((count / max) * 100);
        return (
          <li key={key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
            <div>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-ink">
                  {key}
                  <span className="ml-2 text-xs text-ink-muted">{readableLabel(key)}</span>
                </span>
              </div>
              <div className="mt-1 h-1.5 rounded-sm bg-neutral-soft" aria-hidden="true">
                <div className="h-1.5 rounded-sm bg-brand" style={{ width: `${width}%` }} />
              </div>
            </div>
            <span className="text-sm font-medium tabular-nums text-ink">{count}</span>
          </li>
        );
      })}
    </ul>
  );
}
