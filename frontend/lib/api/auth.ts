import { apiRequest } from "@/lib/api/client";

export type CurrentUser = {
  user_id: string;
  tenant_id: string;
  email: string;
  role: string;
};

export function login(email: string, password: string): Promise<CurrentUser> {
  return apiRequest("/auth/login", { method: "POST", body: { email, password } });
}

export function logout(): Promise<{ status: string }> {
  return apiRequest("/auth/logout", { method: "POST" });
}

export function currentUser(signal?: AbortSignal): Promise<CurrentUser> {
  return apiRequest("/auth/me", { signal });
}
