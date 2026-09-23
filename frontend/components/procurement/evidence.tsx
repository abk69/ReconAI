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
  const scalars = entries.filter(([, value]) => isScalar(value));

  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-ink-muted">{description}</p>
      {scalars.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">No scalar evidence fields were stored.</p>
      ) : (
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {scalars.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">{key}</dt>
              <dd className="mt-1 text-sm text-ink">{value === null ? "null" : String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm text-brand">View raw evidence</summary>
        <pre className="mt-2 overflow-x-auto rounded-md bg-canvas p-3 text-xs text-ink">
          {JSON.stringify(evidence, null, 2)}
        </pre>
      </details>
    </section>
  );
}
