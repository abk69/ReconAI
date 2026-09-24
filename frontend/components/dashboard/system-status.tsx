"use client";

import { useEffect, useState } from "react";

import { ErrorState, LoadingState } from "@/components/ui/state";
import { explainApiError } from "@/lib/api/errors";
import { getHealth } from "@/lib/api/health";
import type { HealthResponse } from "@/types/api";

type Status =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "error"; message: string };

export function SystemStatus() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then((health) => setStatus({ kind: "ok", health }))
      .catch((error: unknown) => {
        setStatus({ kind: "error", message: explainApiError(error, "Health check") });
      });
    return () => controller.abort();
  }, []);

  return (
    <section aria-labelledby="system-status-heading" className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 id="system-status-heading" className="text-base font-semibold text-ink">
        System status
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Backend integration is being established. This probe calls the existing GET /health endpoint.
      </p>
      <div className="mt-4">
        {status.kind === "loading" ? (
          <LoadingState
            title="Checking backend"
            description="Checking whether the service is reachable."
          />
        ) : null}
        {status.kind === "error" ? (
          <ErrorState
            title="Backend not reachable"
            description={status.message}
          />
        ) : null}
        {status.kind === "ok" ? (
          <p className="text-sm text-ink">
            <span className="font-medium">Reachable.</span>{" "}
            Service <span className="font-medium">{status.health.service}</span> reported status{" "}
            <span className="font-medium">{status.health.status}</span>.
          </p>
        ) : null}
      </div>
    </section>
  );
}
