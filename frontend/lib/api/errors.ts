import type { ApiErrorBody } from "@/types/api";

export type ApiErrorCategory =
  | "unavailable"
  | "timeout"
  | "bad_request"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "invalid"
  | "rate_limited"
  | "server"
  | "malformed"
  | "unknown";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly category: ApiErrorCategory;

  constructor(body: ApiErrorBody & { category?: ApiErrorCategory }) {
    super(body.message);
    this.name = "ApiError";
    this.status = body.status;
    this.detail = body.detail;
    this.category = body.category ?? categoryForStatus(body.status);
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function categoryForStatus(status: number): ApiErrorCategory {
  if (status === 400) return "bad_request";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "invalid";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "server";
  if (status === 0) return "unavailable";
  return "unknown";
}

export function explainApiError(error: unknown, label: string): string {
  if (!isApiError(error)) {
    return `${label} could not be loaded.`;
  }
  const safe = safeDetail(error.message);
  switch (error.category) {
    case "timeout":
      return `${label} took too long. Try again.`;
    case "unavailable":
      return `${label} could not reach the service.`;
    case "not_found":
      return `${label} was not found.`;
    case "unauthorized":
      return `${label} was refused. This workspace is not signed in.`;
    case "forbidden":
      return `You do not have permission for ${label}.`;
    case "conflict":
      return safe
        ? `${label} conflicts with a stored record. ${safe}`
        : `${label} conflicts with a stored record. Refresh and try again.`;
    case "invalid":
      return safe
        ? `${label} was not accepted. ${safe}`
        : `${label} was not accepted. Check the values and try again.`;
    case "bad_request":
      return safe
        ? `${label} could not be completed. ${safe}`
        : `${label} could not be completed with the information sent.`;
    case "rate_limited":
      return `Too many requests. Wait a moment and try ${label} again.`;
    case "server":
      return `${label} could not be completed. The service reported an error.`;
    case "malformed":
      return `${label} returned a response this workspace could not read.`;
    default:
      return `${label} could not be loaded.`;
  }
}

/** Keep a short backend sentence. Drop traces, markup, and long dumps. */
export function safeDetail(value: string): string | null {
  const trimmed = value.replace(/\s+/g, " ").trim();
  if (!trimmed || trimmed.length > 180) return null;
  if (/traceback|exception|sqlalchemy|password|secret|api[_-]?key|bearer\s+/i.test(trimmed)) {
    return null;
  }
  if (/[<>]/.test(trimmed) || /file "\//i.test(trimmed)) return null;
  if (/^request failed \(\d+\)$/i.test(trimmed)) return null;
  return trimmed;
}
