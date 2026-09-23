import { getApiBaseUrl } from "@/lib/config/env";

export const apiConfig = {
  baseUrl: getApiBaseUrl(),
  defaultTimeoutMs: 10_000,
};
