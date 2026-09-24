export function FlowRail({
  label,
  steps,
}: {
  label: string;
  steps: { id: string; label: string; stored: boolean }[];
}) {
  return (
    <ol aria-label={label} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
      {steps.map((step, index) => (
        <li
          key={step.id}
          aria-current={step.stored ? "step" : undefined}
          className={`rounded-xl border px-3 py-2 ${
            step.stored
              ? "border-brand/30 bg-success-soft text-ink"
              : "border-line bg-surface text-ink-muted"
          }`}
        >
          <span className="text-[11px] tracking-[0.14em] uppercase">{String(index + 1).padStart(2, "0")}</span>
          <p className="text-sm font-medium">{step.label}</p>
          <p className="text-[11px] tracking-wide uppercase">{step.stored ? "Stored" : "Not stored"}</p>
        </li>
      ))}
    </ol>
  );
}
