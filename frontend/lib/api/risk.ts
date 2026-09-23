import { apiRequest } from "@/lib/api/client";
import { withQuery } from "@/lib/api/query";
import type {
  AnomalyPage,
  AnomalySignal,
  AnomalySummary,
  AnomalyTrends,
  RiskHistory,
  RiskProfileList,
  ScanList,
} from "@/types/risk";

export function listRiskProfiles(
  params: { entity_type?: string; risk_band?: string; limit?: number; offset?: number },
  signal?: AbortSignal,
): Promise<RiskProfileList> {
  return apiRequest(withQuery("/risk/profiles", params), { signal });
}

export function getRiskHistory(
  entityType: string,
  entityId: string,
  asOf?: string,
  signal?: AbortSignal,
): Promise<RiskHistory> {
  return apiRequest(withQuery(`/risk/profiles/${entityType}/${entityId}`, { as_of: asOf }), {
    signal,
  });
}

export function listAnomalies(
  params: {
    anomaly_type?: string;
    severity?: string;
    vendor_id?: string;
    invoice_id?: string;
    purchase_order_id?: string;
    detected_from?: string;
    detected_to?: string;
    high_or_critical?: boolean;
    limit?: number;
    cursor?: string;
  },
  signal?: AbortSignal,
): Promise<AnomalyPage> {
  return apiRequest(
    withQuery("/anomalies", {
      ...params,
      high_or_critical: params.high_or_critical ? "true" : undefined,
    }),
    { signal },
  );
}

export function getAnomaly(id: string, signal?: AbortSignal): Promise<AnomalySignal> {
  return apiRequest(`/anomalies/${id}`, { signal });
}

export function getAnomalySummary(
  params: {
    vendor_id?: string;
    anomaly_type?: string;
    severity?: string;
    start_date?: string;
    end_date?: string;
  },
  signal?: AbortSignal,
): Promise<AnomalySummary> {
  return apiRequest(withQuery("/anomalies/summary", params), { signal });
}

export function getAnomalyTrends(
  params: { period?: string; start_date?: string; end_date?: string },
  signal?: AbortSignal,
): Promise<AnomalyTrends> {
  return apiRequest(withQuery("/anomalies/trends", params), { signal });
}

export function listScans(
  params: { status?: string; scan_type?: string; limit?: number; offset?: number },
  signal?: AbortSignal,
): Promise<ScanList> {
  return apiRequest(withQuery("/anomalies/scans", params), { signal });
}
