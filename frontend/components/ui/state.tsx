type StatePanelProps = {
  title: string;
  description: string;
};

export function LoadingState({ title, description }: StatePanelProps) {
  return (
    <div role="status" className="rounded-md border border-line bg-surface px-4 py-5 shadow-card">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 text-sm text-ink-muted">{description}</p>
      <div className="mt-4">
        <SkeletonBlock label={title} />
      </div>
    </div>
  );
}

export function ErrorState({ title, description }: StatePanelProps) {
  return (
    <div role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-4 py-5">
      <p className="text-sm font-medium text-danger">{title}</p>
      <p className="mt-1 text-sm text-ink">{description}</p>
    </div>
  );
}

export function EmptyState({ title, description }: StatePanelProps) {
  return (
    <div className="rounded-md border border-dashed border-line bg-canvas px-4 py-6">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 text-sm text-ink-muted">{description}</p>
    </div>
  );
}

export function SkeletonBlock({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="animate-pulse space-y-2">
      <div className="h-3 w-1/3 rounded-sm bg-line" />
      <div className="h-3 w-full rounded-sm bg-neutral-soft" />
      <div className="h-3 w-5/6 rounded-sm bg-neutral-soft" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
