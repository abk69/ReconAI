/** Shared API contracts. Names match backend terminology. */

export type ApiErrorBody = {
  status: number;
  message: string;
  detail?: unknown;
};

export type PageParams = {
  limit?: number;
  cursor?: string | null;
};

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  limit: number;
};

export type HealthResponse = {
  status: string;
  service: string;
};
