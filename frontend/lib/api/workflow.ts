import { apiRequest } from "@/lib/api/client";
import { withQuery } from "@/lib/api/query";
import type {
  ActionApproval,
  ActionDecision,
  ActionExecuteResult,
  ActionExecution,
  AuditEvent,
  FieldCorrection,
  PolicyGroundingList,
  PromoteResult,
  ResolutionPlan,
  ResolutionPlanList,
  ReviewTask,
  ReviewTaskList,
} from "@/types/workflow";

export function listPolicyGrounding(
  exceptionId: string,
  signal?: AbortSignal,
): Promise<PolicyGroundingList> {
  return apiRequest(`/reconciliation/exceptions/${exceptionId}/policy-grounding`, { signal });
}

export function listReviewTasks(
  params: {
    q?: string;
    status?: string;
    document_type?: string;
    priority?: string;
    document_id?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<ReviewTaskList> {
  return apiRequest(withQuery("/review/tasks", params), { signal });
}

export function getReviewTask(id: string, signal?: AbortSignal): Promise<ReviewTask> {
  return apiRequest(`/review/tasks/${id}`, { signal });
}

export function approveReviewTask(
  id: string,
  body: { reviewer?: string; reason?: string },
): Promise<ReviewTask> {
  return apiRequest(`/review/tasks/${id}/approve`, { method: "POST", body });
}

export function correctReviewTask(
  id: string,
  body: { reviewer?: string; reason?: string; corrections: FieldCorrection[] },
): Promise<ReviewTask> {
  return apiRequest(`/review/tasks/${id}/correct`, { method: "POST", body });
}

export function rejectReviewTask(
  id: string,
  body: { reviewer?: string; reason?: string },
): Promise<ReviewTask> {
  return apiRequest(`/review/tasks/${id}/reject`, { method: "POST", body });
}

export function promoteReviewTask(id: string): Promise<PromoteResult> {
  return apiRequest(`/review/tasks/${id}/promote`, { method: "POST", body: {} });
}

export function listResolutionPlans(
  params: {
    status?: string;
    reconciliation_exception_id?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<ResolutionPlanList> {
  return apiRequest(withQuery("/resolution-plans", params), { signal });
}

export function getResolutionPlan(id: string, signal?: AbortSignal): Promise<ResolutionPlan> {
  return apiRequest(`/resolution-plans/${id}`, { signal });
}

export function listApprovals(planId: string, signal?: AbortSignal): Promise<{ items: ActionApproval[]; count: number }> {
  return apiRequest(`/resolution-plans/${planId}/approvals`, { signal });
}

export function listExecutions(
  planId: string,
  signal?: AbortSignal,
): Promise<{ items: ActionExecution[]; count: number }> {
  return apiRequest(`/resolution-plans/${planId}/executions`, { signal });
}

export function listAudit(
  planId: string,
  signal?: AbortSignal,
): Promise<{ plan_id: string; events: AuditEvent[]; count: number }> {
  return apiRequest(`/resolution-plans/${planId}/audit`, { signal });
}

export function approveProposedAction(
  planId: string,
  actionId: string,
  body: { reviewer: string; comment?: string; idempotency_key?: string },
): Promise<ActionDecision> {
  return apiRequest(`/resolution-plans/${planId}/actions/${actionId}/approve`, {
    method: "POST",
    body,
  });
}

export function rejectProposedAction(
  planId: string,
  actionId: string,
  body: { reviewer: string; comment?: string; idempotency_key?: string },
): Promise<ActionDecision> {
  return apiRequest(`/resolution-plans/${planId}/actions/${actionId}/reject`, {
    method: "POST",
    body,
  });
}

export function executeProposedAction(
  planId: string,
  actionId: string,
  idempotencyKey: string,
): Promise<ActionExecuteResult> {
  return apiRequest(`/resolution-plans/${planId}/actions/${actionId}/execute`, {
    method: "POST",
    body: { idempotency_key: idempotencyKey },
  });
}
