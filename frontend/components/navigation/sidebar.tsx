"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { useState } from "react";

import { navigation } from "@/lib/navigation";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="flex flex-col gap-6">
      {navigation.map((section) => (
        <div key={section.id}>
          <p className="px-3 text-[11px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
            {section.label}
          </p>
          <ul className="mt-2 space-y-0.5">
            {section.items.map((item) => {
              const active = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-md px-3 py-2 text-sm transition-colors ${
                      active
                        ? "bg-brand text-white"
                        : "text-ink hover:bg-neutral-soft"
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
        <span className="text-sm font-semibold tracking-[0.18em] text-brand">RECONAI</span>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-md border border-line px-2.5 py-1.5 text-sm text-ink"
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X aria-hidden="true" size={16} /> : <Menu aria-hidden="true" size={16} />}
          {open ? "Close" : "Menu"}
        </button>
      </div>

      {open ? (
        <div className="border-b border-line bg-surface px-3 py-4 lg:hidden" id="mobile-nav">
          <NavLinks onNavigate={() => setOpen(false)} />
        </div>
      ) : null}

      <aside className="hidden w-64 shrink-0 border-r border-line bg-surface lg:block">
        <div className="sticky top-0 flex h-screen flex-col px-3 py-5">
          <div className="px-3 pb-6">
            <p className="text-sm font-semibold tracking-[0.2em] text-brand">RECONAI</p>
            <p className="mt-1 text-xs text-ink-muted">Procurement reconciliation</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <NavLinks />
          </div>
        </div>
      </aside>
    </>
  );
}
