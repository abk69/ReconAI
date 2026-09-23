import { apiRequest } from "@/lib/api/client";
import type { HealthResponse } from "@/types/api";

/** Backend liveness probe: GET /health */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health", { signal });
}
