"use client";

import { usePathname } from "next/navigation";

import { findNavItem } from "@/lib/navigation";

export function Header() {
  const pathname = usePathname();
  const current = findNavItem(pathname);

  return (
    <header className="hidden border-b border-line bg-surface px-6 py-4 lg:block">
      <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">ReconAI</p>
      <p className="mt-0.5 text-sm text-ink">{current?.label ?? "Workspace"}</p>
    </header>
  );
}
