"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { login } from "@/lib/api/auth";
import { explainApiError } from "@/lib/api/errors";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <p className="text-[11px] font-medium tracking-[0.2em] text-ink-faint uppercase">ReconAI</p>
      <h1 className="mt-2 text-2xl font-semibold text-ink">Sign in</h1>
      <p className="mt-2 text-sm leading-6 text-ink-muted">
        Access is limited to people provisioned for this workspace. There is no public registration.
      </p>
      <form
        className="mt-6 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          setError(null);
          void login(email, password)
            .then(() => router.push("/dashboard"))
            .catch((caught: unknown) => setError(explainApiError(caught, "Sign in")))
            .finally(() => setBusy(false));
        }}
      >
        <label className="block text-sm">
          Email
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2"
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2"
          />
        </label>
        {error ? (
          <p role="alert" className="text-sm">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={busy}
          className="min-h-10 rounded-md bg-brand px-3 py-2 text-sm text-on-brand disabled:opacity-60"
        >
          {busy ? "Signing in." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
