function isScalar(value: unknown): value is string | number | boolean | null {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

export function EvidencePanel({
  evidence,
  title = "Deterministic reconciliation evidence",
  description = "Stored by the reconciliation engine. These values are not recomputed in the browser, and they are not an AI explanation.",
}: {
  evidence: Record<string, unknown>;
  title?: string;
  description?: string;
}) {
  const entries = Object.entries(evidence);
  const highlightKeys = [
    "expected_unit_price",
    "billed_unit_price",
    "expected_value",
    "actual_value",
    "absolute_variance",
    "variance",
    "percentage_variance",
    "ordered_quantity",
    "received_quantity",
    "invoiced_quantity",
  ];
  const scalars = entries.filter(
    ([key, value]) => isScalar(value) && !highlightKeys.includes(key),
  );
  const highlights = highlightKeys
    .map((key) => [key, evidence[key]] as const)
    .filter((entry): entry is readonly [string, string | number | boolean | null] => isScalar(entry[1]));

  return (
    <section className="surface-fact border-t border-white/10 pt-8">
      <p className="text-[11px] font-medium tracking-[0.16em] text-ink-faint uppercase">Reconciliation finding</p>
      <h2 className="mt-2 text-2xl font-semibold text-ink">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-ink-muted">{description}</p>
      {highlights.length > 0 ? (
        <dl className="mt-6 grid gap-6 sm:grid-cols-3">
          {highlights.map(([key, value]) => (
            <div key={key}>
              <dt className="text-[11px] tracking-[0.14em] text-ink-faint uppercase">{key}</dt>
              <dd className="mt-1 text-3xl font-semibold tabular-nums text-ink">{value === null ? "null" : String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {highlights.length === 0 && scalars.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">No scalar evidence fields were stored.</p>
      ) : scalars.length > 0 ? (
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {scalars.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">{key}</dt>
              <dd className="mt-1 text-sm text-ink">{value === null ? "null" : String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm text-brand">View raw evidence</summary>
        <pre className="mt-2 overflow-x-auto rounded-md bg-canvas p-3 text-xs text-ink">
          {JSON.stringify(evidence, null, 2)}
        </pre>
      </details>
    </section>
  );
}
