import { apiConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
};

function joinUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${apiConfig.baseUrl}${normalized}`;
}

async function readErrorMessage(response: Response): Promise<{ message: string; detail?: unknown }> {
  const text = await response.text();
  if (!text) {
    return { message: `Request failed (${response.status})` };
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      const message = typeof detail === "string" ? detail : `Request failed (${response.status})`;
      return { message, detail };
    }
  } catch {
    return { message: text.slice(0, 300) };
  }
  return { message: text.slice(0, 300) };
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? apiConfig.defaultTimeoutMs;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  try {
    const headers: Record<string, string> = {};
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    // Authentication is not implemented. A future session may set Authorization here.
    // Do not read secrets from NEXT_PUBLIC_* variables.

    const response = await fetch(joinUrl(path), {
      method: options.method ?? "GET",
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const parsed = await readErrorMessage(response);
      throw new ApiError({
        status: response.status,
        message: parsed.message,
        detail: parsed.detail,
      });
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError({
        status: 0,
        message: "The request timed out or was cancelled.",
      });
    }
    const message = error instanceof Error ? error.message : "Network request failed.";
    throw new ApiError({ status: 0, message });
  } finally {
    clearTimeout(timer);
  }
}
