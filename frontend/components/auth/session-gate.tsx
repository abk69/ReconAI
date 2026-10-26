"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { currentUser, logout, type CurrentUser } from "@/lib/api/auth";
import { isApiError } from "@/lib/api/errors";

export function SessionGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "denied">("loading");

  useEffect(() => {
    if (pathname === "/login") {
      return;
    }
    const controller = new AbortController();
    setPhase("loading");
    currentUser(controller.signal)
      .then((next) => {
        setUser(next);
        setPhase("ready");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setUser(null);
        if (isApiError(error) && (error.status === 401 || error.status === 403)) {
          setPhase("denied");
          router.replace("/login");
          return;
        }
        setPhase("denied");
      });
    return () => controller.abort();
  }, [pathname, router]);

  if (pathname === "/login") {
    return children;
  }
  if (phase === "loading") {
    return <p className="text-sm text-ink-muted">Checking your session.</p>;
  }
  if (phase === "denied") {
    return (
      <p role="alert" className="text-sm">
        Sign in to view this workspace.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {user ? (
        <p className="text-sm text-ink-muted">
          {user.email} · {user.role}
          <button
            type="button"
            className="ml-3 text-brand underline"
            onClick={() => {
              void logout().finally(() => router.replace("/login"));
            }}
          >
            Sign out
          </button>
        </p>
      ) : null}
      {children}
    </div>
  );
}
