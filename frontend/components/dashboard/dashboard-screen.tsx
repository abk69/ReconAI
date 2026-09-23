"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ActivityPanel,
  DocumentsPanel,
  ExceptionsPanel,
  KpiRow,
  ReconciliationPanel,
  ReviewPanel,
  RiskPanel,
} from "@/components/dashboard/panels";
import { ErrorState, LoadingState } from "@/components/ui/state";
import { getDashboardSummary } from "@/lib/api/dashboard";
import { isApiError } from "@/lib/api/errors";
import { formatTimestamp } from "@/lib/labels";
import type { DashboardSummary } from "@/types/dashboard";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; summary: DashboardSummary; refreshedAt: string }
  | { kind: "error"; message: string; summary: DashboardSummary | null };

function errorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 0) {
      return `Backend unavailable. ${error.message} Start the API and confirm NEXT_PUBLIC_API_BASE_URL.`;
    }
    return `Dashboard request failed (${error.status}). ${error.message}`;
  }
  return "Dashboard request failed before a response was received.";
}

export function DashboardScreen() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback((replace: boolean) => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    if (!replace) {
      setRefreshing(true);
    }
    getDashboardSummary(controller.signal)
      .then((summary) => {
        if (controller.signal.aborted) {
          return;
        }
        setState({ kind: "ready", summary, refreshedAt: new Date().toISOString() });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setState((current) => ({
          kind: "error",
          message: errorMessage(error),
          summary:
            current.kind === "ready"
              ? current.summary
              : current.kind === "error"
                ? current.summary
                : null,
        }));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setRefreshing(false);
        }
      });
  }, []);

  useEffect(() => {
    load(true);
    return () => requestRef.current?.abort();
  }, [load]);

  const summary = state.kind === "ready" ? state.summary : state.kind === "error" ? state.summary : null;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Dashboard</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
            Procurement reconciliation intelligence from persisted records. Counts come from the
            API. This page does not calculate financial totals.
          </p>
          {state.kind === "ready" ? (
            <p className="mt-2 text-xs text-ink-muted">
              Last refreshed {formatTimestamp(state.refreshedAt)}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink shadow-card disabled:opacity-60"
          disabled={state.kind === "loading" || refreshing}
          onClick={() => load(false)}
        >
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>

      {state.kind === "loading" ? (
        <LoadingState
          title="Loading dashboard"
          description="Requesting GET /dashboard/summary."
        />
      ) : null}

      {state.kind === "error" ? (
        <ErrorState title="Dashboard data unavailable" description={state.message} />
      ) : null}

      {summary ? (
        <>
          <KpiRow summary={summary} />
          <div className="grid gap-4 lg:grid-cols-2">
            <ReconciliationPanel summary={summary} />
            <ExceptionsPanel summary={summary} />
            <RiskPanel summary={summary} />
            <DocumentsPanel summary={summary} />
          </div>
          <ReviewPanel summary={summary} />
          <ActivityPanel summary={summary} />
        </>
      ) : null}
    </div>
  );
}
