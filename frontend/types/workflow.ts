export type PolicyCitation = {
  policy_document_id?: string;
  policy_version_id?: string;
  policy_version_label?: string;
  chunk_id?: string;
  chunk_index?: number;
  section_id?: string | null;
  section_title?: string | null;
  source_filename?: string | null;
  page_number?: number | null;
  content_hash?: string;
  similarity?: number | null;
  content?: string;
  excerpt?: string;
};

export type PolicyGroundingItem = {
  id: string;
  reconciliation_exception_id: string;
  status: string;
  conclusion: string;
  explanation: string;
  policy_support: string;
  limitations: string;
  citations: PolicyCitation[];
  created_at: string;
  model: string | null;
};

export type PolicyGroundingList = {
  items: PolicyGroundingItem[];
  count: number;
};

export type ReviewDecision = {
  id: string;
  action: string;
  field_path: string | null;
  original_value: unknown;
  corrected_value: unknown;
  reason: string | null;
  reviewer: string | null;
  evidence_ref: string | null;
  created_at: string;
};

export type ReviewTask = {
  id: string;
  document_id: string;
  extraction_result_id: string | null;
  status: string;
  reason: string | null;
  priority: string;
  assigned_to: string | null;
  document_type: string | null;
  detected_type: string | null;
  document_status: string | null;
  original_filename: string | null;
  candidate_summary: Record<string, unknown> | null;
  reviewed_candidate: Record<string, unknown> | null;
  original_candidate: Record<string, unknown> | null;
  evidence: unknown[];
  decisions: ReviewDecision[];
  promoted_entity_type: string | null;
  promoted_entity_id: string | null;
  promoted_at: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type ReviewTaskList = {
  items: ReviewTask[];
  count: number;
  total: number;
  limit: number | null;
  offset: number;
};

export type FieldCorrection = {
  field_path: string;
  corrected_value: string;
  reason?: string;
};

export type PromoteResult = {
  review_task_id: string;
  status: string;
  document_id: string;
  document_status: string;
  promoted_entity_type: string | null;
  promoted_entity_id: string | null;
  promoted_at: string | null;
};

export type ResolutionPlanListItem = {
  id: string;
  reconciliation_exception_id: string;
  status: string;
  reasoning_summary: string;
  proposed_by: string | null;
  planner_model: string | null;
  created_at: string;
  action_count: number;
  exception_type: string | null;
  exception_message: string | null;
};

export type ResolutionPlanList = {
  items: ResolutionPlanListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type ProposedAction = {
  id: string;
  resolution_plan_id: string;
  action_type: string;
  action_order: number;
  parameters: Record<string, unknown>;
  rationale: string;
  requires_approval: boolean;
  status: string;
  approved_parameters_hash: string | null;
  created_at: string;
  updated_at: string;
};

export type ResolutionPlan = {
  id: string;
  reconciliation_exception_id: string;
  status: string;
  reasoning_summary: string;
  policy_grounding_result_id: string | null;
  proposed_by: string | null;
  planning_key: string | null;
  planner_model: string | null;
  prompt_version: string | null;
  limitations: string;
  planning_latency_ms: number | null;
  created_at: string;
  updated_at: string;
  actions: ProposedAction[];
};

export type ActionApproval = {
  id: string;
  proposed_action_id: string;
  decision: string;
  reviewer: string;
  reason: string | null;
  decided_at: string;
  created_at: string;
  idempotency_key: string | null;
};

export type ActionExecution = {
  id: string;
  proposed_action_id: string;
  execution_status: string;
  idempotency_key: string;
  started_at: string | null;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
  proposed_action_id: string | null;
  action_execution_id: string | null;
  created_at: string;
  data: Record<string, unknown>;
};

export type ActionDecision = {
  plan_id: string;
  action_id: string;
  action_type: string;
  action_status: string;
  plan_status: string;
  approval_id: string;
  decision: string;
  reviewer: string;
  comment: string | null;
  decided_at: string;
  reused_existing: boolean;
};

export type ActionExecuteResult = {
  plan_id: string;
  action_id: string;
  action_type: string;
  execution_id: string;
  execution_status: string;
  action_status: string;
  plan_status: string;
  idempotency_key: string;
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
};
