import { apiConfig } from "@/lib/api/config";
import { ApiError, categoryForStatus, safeDetail } from "@/lib/api/errors";
import { recordDiagnostic } from "@/lib/observability/diagnostics";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
  timeoutMs?: number;
};

function joinUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${apiConfig.baseUrl}${normalized}`;
}

function safeServerMessage(response: Response, text: string): string {
  if (!text) {
    return `Request failed (${response.status})`;
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return safeDetail(detail) ?? `Request failed (${response.status})`;
      }
    }
  } catch {
    return safeDetail(text) ?? `Request failed (${response.status})`;
  }
  return `Request failed (${response.status})`;
}

function fail(method: string, status: number, message: string, category = categoryForStatus(status)): never {
  recordDiagnostic({ method, status, category });
  throw new ApiError({ status, message, category });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? apiConfig.defaultTimeoutMs;
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  try {
    const headers: Record<string, string> = {};
    let body: BodyInit | undefined;
    if (options.formData) {
      // Leave Content-Type unset so the browser supplies the multipart boundary.
      body = options.formData;
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
    // Authentication is not implemented. A future session may set Authorization here.
    // Do not read secrets from NEXT_PUBLIC_* variables.

    const response = await fetch(joinUrl(path), {
      method,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body,
      signal: controller.signal,
    });

    if (!response.ok) {
      const text = await response.text();
      fail(method, response.status, safeServerMessage(response, text));
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const text = await response.text();
    if (!text) {
      return undefined as T;
    }
    try {
      return JSON.parse(text) as T;
    } catch {
      fail(method, response.status, "Response was not valid JSON.", "malformed");
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (options.signal?.aborted) {
      throw error;
    }
    if (timedOut || (error instanceof DOMException && error.name === "AbortError")) {
      fail(method, 0, "The request timed out.", "timeout");
    }
    fail(method, 0, "Network request failed.", "unavailable");
  } finally {
    clearTimeout(timer);
  }
}
