import { apiRequest } from "@/lib/api/client";
import { withQuery } from "@/lib/api/query";
import type {
  PolicyDocument,
  PolicyList,
  PolicySearchResult,
  PolicyVersionDetail,
  PolicyVersionList,
} from "@/types/policies";

export function listPolicies(
  params: { version_status?: string; limit?: number; offset?: number },
  signal?: AbortSignal,
): Promise<PolicyList> {
  return apiRequest(withQuery("/policies", params), { signal });
}

export function getPolicy(id: string, signal?: AbortSignal): Promise<PolicyDocument> {
  return apiRequest(`/policies/${id}`, { signal });
}

export function listPolicyVersions(id: string, signal?: AbortSignal): Promise<PolicyVersionList> {
  return apiRequest(`/policies/${id}/versions`, { signal });
}

export function getPolicyVersion(
  policyId: string,
  versionId: string,
  signal?: AbortSignal,
): Promise<PolicyVersionDetail> {
  return apiRequest(`/policies/${policyId}/versions/${versionId}`, { signal });
}

export function searchPolicyVersion(
  policyId: string,
  versionId: string,
  body: { query: string; top_k: number },
): Promise<PolicySearchResult> {
  return apiRequest(`/policies/${policyId}/versions/${versionId}/search`, {
    method: "POST",
    body,
  });
}
