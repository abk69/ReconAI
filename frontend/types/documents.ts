export type ValidationIssue = {
  code?: string;
  message?: string;
  field_name?: string | null;
  severity?: string;
};

export type ValidationResult = {
  is_valid?: boolean;
  requires_review?: boolean;
  issues?: ValidationIssue[];
};

export type FieldEvidence = {
  field_name?: string;
  value?: unknown;
  raw_value?: string | null;
  source_type?: string;
  page?: number | null;
  sheet?: string | null;
  cell?: string | null;
  source_text?: string | null;
  snippet?: string | null;
  extraction_method?: string;
  confidence?: string;
  reason?: string | null;
};

export type UnderstandingResult = {
  document_id: string;
  detected_type: string;
  outcome: string;
  document_status: string;
  message: string | null;
  candidate: Record<string, unknown> | null;
  validation: ValidationResult;
  evidence: FieldEvidence[];
  extractor_version: string;
  has_raw_extraction: boolean;
};

export type FieldDiff = {
  field_path?: string;
  status?: string;
  m4_value?: unknown;
  gemini_value?: unknown;
};

export type StoredComparison = {
  agreements?: string[];
  disagreements?: FieldDiff[];
  m4_only?: FieldDiff[];
  gemini_only?: FieldDiff[];
  missing?: string[];
  financially_significant_disagreements?: FieldDiff[];
  has_financial_disagreement?: boolean;
};

export type LlmUnderstanding = {
  id: string;
  document_id: string;
  m4_extraction_result_id: string | null;
  provider: string;
  model: string;
  prompt_version: string;
  invocation_status: string;
  application_quality: string | null;
  quality_reasons: string[];
  gate_reasons: string[];
  candidate: Record<string, unknown> | null;
  evidence: FieldEvidence[];
  validation: ValidationResult;
  comparison: StoredComparison | null;
  evidence_check: {
    is_grounded?: boolean;
    unsupported_fields?: string[];
    details?: unknown[];
  } | null;
  usage: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
  } | null;
  message: string | null;
  error_code: string | null;
  error_message: string | null;
  document_status: string | null;
  created_at: string;
};

export type RawExtraction = {
  document_id: string;
  raw_extraction: Record<string, unknown>;
};
