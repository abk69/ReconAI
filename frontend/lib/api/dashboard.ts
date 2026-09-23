import { apiRequest } from "@/lib/api/client";
import type { DashboardSummary } from "@/types/dashboard";

/** Read-only aggregate. Does not calculate financial truth in the browser. */
export function getDashboardSummary(signal?: AbortSignal): Promise<DashboardSummary> {
  return apiRequest<DashboardSummary>("/dashboard/summary", { signal });
}
