"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

export function FilterBar({
  fields,
}: {
  fields: { name: string; label: string; options?: string[] }[];
}) {
  const params = useSearchParams();
  const router = useRouter();
  const [draft, setDraft] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of fields) {
      initial[field.name] = params.get(field.name) ?? "";
    }
    return initial;
  });

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
              {field.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
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
      <button type="submit" className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm">
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
