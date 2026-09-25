import { apiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { LlmUnderstanding, RawExtraction, UnderstandingResult } from "@/types/documents";

export type DocumentUploadResult = {
  id: string;
  isDuplicate: boolean;
};

const UPLOAD_TIMEOUT_MS = 60_000;

export async function uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentUploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  const payload = await apiRequest<unknown>("/documents", {
    method: "POST",
    formData: form,
    signal,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  });
  if (!payload || typeof payload !== "object") {
    throw new ApiError({ status: 200, message: "Response was not valid JSON.", category: "malformed" });
  }
  const id = (payload as { id?: unknown }).id;
  if (typeof id !== "string" || id.length === 0) {
    throw new ApiError({ status: 200, message: "Response was not valid JSON.", category: "malformed" });
  }
  return {
    id,
    isDuplicate: (payload as { is_duplicate?: unknown }).is_duplicate === true,
  };
}

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
