import type { ReactNode } from "react";

export type Column<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption: string;
}) {
  return (
    <div>
      <ul className="space-y-6 md:hidden">
        {rows.map((row) => (
          <li key={rowKey(row)} className="border-b border-line pb-5">
            <dl className="space-y-3">
              {columns.map((column) => (
                <div key={column.key}>
                  <dt className="text-[11px] font-medium tracking-[0.14em] text-ink-faint uppercase">{column.header}</dt>
                  <dd className="mt-1 text-sm text-ink">{column.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto md:block" tabIndex={0} aria-label={caption}>
        <table className="min-w-full border-collapse text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-line">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className="px-2 py-3 text-[11px] font-medium tracking-[0.14em] text-ink-faint uppercase"
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-white/5 transition-colors duration-200 last:border-0 hover:bg-white/[0.03]">
                {columns.map((column) => (
                  <td key={column.key} className="px-2 py-3.5 align-top text-ink">
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Pager({
  offset,
  limit,
  total,
  onPage,
}: {
  offset: number;
  limit: number;
  total: number;
  onPage: (offset: number) => void;
}) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p className="text-ink-muted">
        Showing {start}–{end} of {total}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          className="min-h-10 rounded-lg border border-line px-3 py-1.5 text-ink transition-colors duration-150 hover:bg-hover disabled:opacity-40"
          disabled={offset <= 0}
          onClick={() => onPage(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          type="button"
          className="min-h-10 rounded-lg border border-line px-3 py-1.5 text-ink transition-colors duration-150 hover:bg-hover disabled:opacity-40"
          disabled={offset + limit >= total}
          onClick={() => onPage(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
