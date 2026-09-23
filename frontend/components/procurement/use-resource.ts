"use client";

import { useEffect, useRef, useState } from "react";

import { isApiError } from "@/lib/api/errors";

export type ResourceState<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "error"; message: string };

export function resourceError(error: unknown, label: string): string {
  if (isApiError(error)) {
    if (error.status === 0) {
      return `Backend unavailable. ${error.message}`;
    }
    if (error.status === 404) {
      return `${label} was not found.`;
    }
    return `${label} request failed (${error.status}). ${error.message}`;
  }
  return `${label} request failed before a response was received.`;
}

export function useResource<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
  label: string,
): ResourceState<T> {
  const loadRef = useRef(load);
  loadRef.current = load;
  const [state, setState] = useState<ResourceState<T>>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    loadRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ kind: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ kind: "error", message: resourceError(error, label) });
        }
      });
    return () => controller.abort();
  }, [key, label]);

  return state;
}
