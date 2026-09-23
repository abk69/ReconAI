import { EmptyState } from "@/components/ui/state";

type PlaceholderSectionProps = {
  title: string;
  description: string;
};

export function PlaceholderSection({ title, description }: PlaceholderSectionProps) {
  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <span className="shrink-0 rounded-sm border border-line bg-neutral-soft px-2 py-0.5 text-xs font-medium text-neutral">
          Not available yet
        </span>
      </div>
      <div className="mt-4">
        <EmptyState title="No data yet" description={description} />
      </div>
    </section>
  );
}
