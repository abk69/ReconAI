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
    <div className="overflow-x-auto rounded-md border border-line" tabIndex={0}>
      <table className="min-w-full border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-line bg-canvas">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className="px-3 py-2 text-xs font-medium tracking-wide text-ink-muted uppercase">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-line last:border-0">
              {columns.map((column) => (
                <td key={column.key} className="px-3 py-2 align-top text-ink">
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
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
          className="rounded-md border border-line bg-surface px-3 py-1.5 disabled:opacity-50"
          disabled={offset <= 0}
          onClick={() => onPage(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          type="button"
          className="rounded-md border border-line bg-surface px-3 py-1.5 disabled:opacity-50"
          disabled={offset + limit >= total}
          onClick={() => onPage(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
