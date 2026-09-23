export type RiskProfile = {
  id: string;
  entity_type: string;
  entity_id: string;
  score: number;
  risk_band: string;
  score_version: string;
  as_of: string;
  calculated_at: string;
  signal_count: number;
  breakdown: RiskBreakdown;
  fingerprint: string;
  created_at: string;
  note: string;
};

export type RiskBreakdown = {
  contributing_signals?: ContributingSignal[];
  type_breakdown?: TypeBreakdownRow[];
  formula_notes?: string;
  severity_distribution?: Record<string, number>;
};

export type ContributingSignal = {
  anomaly_type?: string;
  severity?: string;
  base_weight?: string;
  severity_multiplier?: string;
  recency_multiplier?: string;
  raw_contribution?: string;
  capped_contribution?: string | null;
  signal_id?: string;
  signal_fingerprint?: string;
  detected_at?: string;
};

export type TypeBreakdownRow = {
  anomaly_type?: string;
  contribution?: string;
  uncapped_contribution?: string;
  signal_count?: number;
  cap?: string;
};

export type RiskProfileListItem = {
  id: string;
  entity_type: string;
  entity_id: string;
  entity_label: string | null;
  score: number;
  risk_band: string;
  score_version: string;
  as_of: string;
  calculated_at: string;
  signal_count: number;
};

export type RiskProfileList = {
  items: RiskProfileListItem[];
  total: number;
  limit: number;
  offset: number;
  counts_by_band: Record<string, number>;
};

export type RiskHistory = {
  entity_type: string;
  entity_id: string;
  entity_label: string | null;
  current: RiskProfile | null;
  history: RiskProfile[];
};

export type AnomalySignal = {
  id: string;
  anomaly_type: string;
  severity: string;
  score: string;
  vendor_id: string | null;
  purchase_order_id: string | null;
  invoice_id: string | null;
  grn_id: string | null;
  title: string;
  explanation: string;
  evidence: Record<string, unknown>;
  fingerprint: string;
  detected_at: string;
  created_at: string;
};

export type AnomalyPage = {
  items: AnomalySignal[];
  next_cursor: string | null;
  limit: number;
};

export type AnomalySummary = {
  total_signals: number;
  counts_by_type: Record<string, number>;
  counts_by_severity: Record<string, number>;
  counts_by_date: Record<string, number>;
  unique_affected_vendors: number;
  unique_affected_invoices: number;
  unique_affected_pos: number;
};

export type AnomalyTrends = {
  period: string;
  points: { period: string; count: number; high_or_critical: number }[];
};

export type ScanJob = {
  id: string;
  scan_type: string;
  status: string;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
  processed_count: number;
  anomaly_count: number;
  error_count: number;
  error_message: string | null;
};

export type ScanList = {
  items: ScanJob[];
  total: number;
  limit: number;
  offset: number;
};
