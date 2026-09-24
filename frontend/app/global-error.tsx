"use client";

import { useEffect } from "react";

import { recordDiagnostic } from "@/lib/observability/diagnostics";

import "./globals.css";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    recordDiagnostic({ method: "GET", status: 0, category: "render" });
  }, []);

  return (
    <html lang="en">
      <body className="min-h-screen bg-canvas px-4 py-10 text-ink antialiased">
        <div role="alert" className="mx-auto max-w-lg rounded-xl border border-danger/30 bg-danger-soft px-4 py-5">
          <p className="text-[11px] font-medium tracking-[0.14em] text-danger uppercase">ReconAI</p>
          <p className="mt-2 text-sm font-medium">The workspace could not be shown.</p>
          <p className="mt-1 text-sm leading-6 text-ink-muted">Reload the page to try again.</p>
          <button
            type="button"
            className="mt-4 min-h-10 rounded-lg border border-line bg-elevated px-3 py-2 text-sm text-ink"
            onClick={reset}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
