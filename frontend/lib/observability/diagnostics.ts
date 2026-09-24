export type DiagnosticEvent = {
  at: string;
  route: string;
  method: string;
  status: number;
  category: string;
};

const events: DiagnosticEvent[] = [];
const LIMIT = 30;

export function recordDiagnostic(input: {
  method: string;
  status: number;
  category: string;
}): void {
  const route = typeof window === "undefined" ? "" : window.location.pathname;
  events.push({
    at: new Date().toISOString(),
    route,
    method: input.method,
    status: input.status,
    category: input.category,
  });
  if (events.length > LIMIT) {
    events.shift();
  }
}

export function recentDiagnostics(): readonly DiagnosticEvent[] {
  return events;
}
