type StatePanelProps = {
  title: string;
  description: string;
};

export function LoadingState({ title, description }: StatePanelProps) {
  return (
    <div role="status" className="rounded-xl border border-line bg-surface px-4 py-5 shadow-card">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 text-sm text-ink-muted">{description}</p>
      <div className="mt-4 space-y-2" aria-hidden="true">
        <div className="skeleton h-3 w-1/3 rounded-full" />
        <div className="skeleton h-10 w-full rounded-lg" />
        <div className="skeleton h-10 w-full rounded-lg" />
        <div className="skeleton h-10 w-5/6 rounded-lg" />
      </div>
      <span className="sr-only">{title}</span>
    </div>
  );
}

export function ErrorState({ title, description }: StatePanelProps) {
  const unavailable = /could not reach the service/i.test(description);
  const timedOut = /took too long/i.test(description);
  return (
    <div role="alert" className="rounded-xl border border-danger/30 bg-danger-soft px-4 py-5">
      <p className="text-[11px] font-medium tracking-[0.14em] text-danger uppercase">
        {unavailable ? "Service unavailable" : timedOut ? "Timed out" : "Request failed"}
      </p>
      <p className="mt-2 text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 text-sm leading-6 text-ink-muted">{description}</p>
    </div>
  );
}

export function EmptyState({ title, description }: StatePanelProps) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-elevated/40 px-4 py-8 text-center">
      <p className="text-[11px] font-medium tracking-[0.16em] text-ink-faint uppercase">No data</p>
      <p className="mt-2 text-sm font-medium text-ink">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm leading-6 text-ink-muted">{description}</p>
    </div>
  );
}

export function SkeletonBlock({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      <div className="skeleton h-3 w-1/3 rounded-full" />
      <div className="skeleton h-3 w-full rounded-full" />
      <div className="skeleton h-3 w-5/6 rounded-full" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
