import { apiRequest } from "@/lib/api/client";
import type { LlmUnderstanding, RawExtraction, UnderstandingResult } from "@/types/documents";

export function getUnderstanding(
  documentId: string,
  signal?: AbortSignal,
): Promise<UnderstandingResult> {
  return apiRequest(`/documents/${documentId}/understanding`, { signal });
}

export function getLlmUnderstanding(
  documentId: string,
  signal?: AbortSignal,
): Promise<LlmUnderstanding> {
  return apiRequest(`/documents/${documentId}/llm-understanding`, { signal });
}

export function getRawExtraction(documentId: string, signal?: AbortSignal): Promise<RawExtraction> {
  return apiRequest(`/documents/${documentId}/raw-extraction`, { signal });
}
