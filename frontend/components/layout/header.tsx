"use client";

import { usePathname } from "next/navigation";

import { findNavItem } from "@/lib/navigation";

export function Header() {
  const pathname = usePathname();
  const current = findNavItem(pathname);
  const detail = current && pathname !== current.item.href;

  return (
    <header className="hidden px-8 pt-7 lg:block">
      <p className="text-[11px] font-medium tracking-[0.2em] text-ink-faint uppercase">
        ReconAI
        {current ? ` / ${current.section.label}` : ""}
        {detail ? " / Detail" : ""}
      </p>
      <p className="mt-1 text-lg text-ink">{current?.item.label ?? "Workspace"}</p>
    </header>
  );
}
