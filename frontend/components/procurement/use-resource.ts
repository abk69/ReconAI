"use client";

import { useEffect, useRef, useState } from "react";

import { explainApiError, isApiError } from "@/lib/api/errors";

export type ResourceState<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "error"; message: string };

export function resourceError(error: unknown, label: string): string {
  return explainApiError(error, label);
}

export async function loadAside<T>(
  request: Promise<T>,
  label: string,
): Promise<{ value: T | null; error: string | null }> {
  try {
    return { value: await request, error: null };
  } catch (error) {
    if (isApiError(error) && error.status === 404) return { value: null, error: null };
    return { value: null, error: resourceError(error, label) };
  }
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
