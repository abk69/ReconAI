/** GET /dashboard/summary. Field names match the backend response. */

export type CountMap = {
  total: number;
  counts: Record<string, number>;
};

export type DashboardExceptionItem = {
  id: string;
  exception_type: string;
  severity: string;
  status: string;
  message: string;
  invoice_number: string | null;
  po_number: string | null;
  grn_number: string | null;
  created_at: string;
};

export type DashboardRiskProfileItem = {
  id: string;
  entity_type: string;
  entity_id: string;
  score: number;
  risk_band: string;
  score_version: string;
  as_of: string;
  signal_count: number;
  calculated_at: string;
};

export type DashboardReviewItem = {
  id: string;
  status: string;
  priority: string;
  reason: string | null;
  document_filename: string;
  created_at: string;
};

export type DashboardActivityItem = {
  kind: string;
  record_id: string;
  occurred_at: string;
  title: string;
  detail: string;
};

export type DashboardSummary = {
  documents: CountMap;
  reconciliation_exceptions: CountMap;
  exception_severity: CountMap;
  open_exception_count: number;
  in_review_exception_count: number;
  open_exceptions: DashboardExceptionItem[];
  anomaly_signals: CountMap;
  risk_profiles: CountMap;
  high_or_critical_risk_count: number;
  latest_risk_profiles: DashboardRiskProfileItem[];
  review_tasks: CountMap;
  pending_review_count: number;
  pending_reviews: DashboardReviewItem[];
  recent_activity: DashboardActivityItem[];
  reconciliation_note: string;
  risk_note: string;
  review_note: string;
  document_note: string;
};
