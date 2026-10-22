"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

export function FilterBar({
  fields,
}: {
  fields: { name: string; label: string; options?: Array<string | { value: string; label: string }> }[];
}) {
  const params = useSearchParams();
  const router = useRouter();
  const appliedKey = fields.map((field) => `${field.name}:${params.get(field.name) ?? ""}`).join("|");
  const [draft, setDraft] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of fields) {
      initial[field.name] = params.get(field.name) ?? "";
    }
    return initial;
  });

  useEffect(() => {
    const next: Record<string, string> = {};
    if (!appliedKey) {
      setDraft(next);
      return;
    }
    for (const pair of appliedKey.split("|")) {
      const index = pair.indexOf(":");
      if (index === -1) continue;
      next[pair.slice(0, index)] = pair.slice(index + 1);
    }
    setDraft(next);
  }, [appliedKey]);

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        const next = new URLSearchParams();
        for (const field of fields) {
          const value = draft[field.name]?.trim();
          if (value) {
            next.set(field.name, value);
          }
        }
        const query = next.toString();
        router.push(query ? `?${query}` : "?");
      }}
    >
      {fields.map((field) => (
        <label key={field.name} className="flex min-w-36 flex-col gap-1 text-xs text-ink-muted">
          {field.label}
          {field.options ? (
            <select
              className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              value={draft[field.name] ?? ""}
              onChange={(event) =>
                setDraft((current) => ({ ...current, [field.name]: event.target.value }))
              }
            >
              <option value="">Any</option>
              {field.options.map((option) => {
                const value = typeof option === "string" ? option : option.value;
                const label = typeof option === "string" ? option : option.label;
                return (
                  <option key={value} value={value}>
                    {label}
                  </option>
                );
              })}
            </select>
          ) : (
            <input
              className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              value={draft[field.name] ?? ""}
              onChange={(event) =>
                setDraft((current) => ({ ...current, [field.name]: event.target.value }))
              }
            />
          )}
        </label>
      ))}
      <button type="submit" className="min-h-10 rounded-lg border border-line bg-elevated px-3 py-1.5 text-sm text-ink">
        Apply
      </button>
    </form>
  );
}

export function useListQuery() {
  const params = useSearchParams();
  const router = useRouter();
  const offset = Number(params.get("offset") ?? "0");
  const safeOffset = Number.isFinite(offset) && offset > 0 ? offset : 0;
  return {
    q: params.get("q") ?? "",
    status: params.get("status") ?? "",
    documentType: params.get("document_type") ?? "",
    extractionOutcome: params.get("extraction_outcome") ?? "",
    reviewStatus: params.get("review_status") ?? "",
    versionStatus: params.get("version_status") ?? "",
    severity: params.get("severity") ?? "",
    exceptionType: params.get("exception_type") ?? "",
    offset: safeOffset,
    setOffset(next: number) {
      const query = new URLSearchParams(params.toString());
      if (next > 0) {
        query.set("offset", String(next));
      } else {
        query.delete("offset");
      }
      router.push(`?${query.toString()}`);
    },
  };
}
