"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  BookOpen,
  ClipboardCheck,
  FileText,
  GitBranch,
  LayoutDashboard,
  Menu,
  Package,
  Receipt,
  Scale,
  Shield,
  ShoppingCart,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { navigation } from "@/lib/navigation";

const icons: Record<string, typeof LayoutDashboard> = {
  "/dashboard": LayoutDashboard,
  "/documents": FileText,
  "/purchase-orders": ShoppingCart,
  "/goods-receipts": Package,
  "/invoices": Receipt,
  "/reconciliation": Scale,
  "/exceptions": AlertTriangle,
  "/review": ClipboardCheck,
  "/risk": Shield,
  "/policies": BookOpen,
  "/resolution": GitBranch,
};

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="flex flex-col gap-5">
      {navigation.map((section) => (
        <div key={section.id} className="border-t border-line pt-4 first:border-t-0 first:pt-0">
          <p className="px-3 text-[11px] font-semibold tracking-[0.16em] text-ink-faint uppercase">
            {section.label}
          </p>
          <ul className="mt-2 space-y-1">
            {section.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = icons[item.href];
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-200 ${
                      active
                        ? "bg-white/[0.04] text-ink shadow-[0_0_28px_rgb(110_231_183/0.12)]"
                        : "text-ink-muted hover:bg-white/[0.03] hover:text-ink"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`h-4 w-0.5 rounded-full ${active ? "bg-brand" : "bg-transparent"}`}
                    />
                    {Icon ? <Icon aria-hidden="true" size={16} /> : null}
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

function Brand() {
  return (
    <div className="px-3 pb-5">
      <p className="text-sm font-semibold tracking-[0.22em] text-ink">RECONAI</p>
      <p className="mt-1 text-xs text-ink-faint">Procurement intelligence</p>
    </div>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-canvas/80 px-4 py-3 backdrop-blur-md lg:hidden">
        <span className="text-sm font-semibold tracking-[0.18em] text-ink">RECONAI</span>
        <button
          type="button"
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-line bg-elevated px-3 text-sm text-ink"
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X aria-hidden="true" size={16} /> : <Menu aria-hidden="true" size={16} />}
          {open ? "Close" : "Menu"}
        </button>
      </div>

      {open ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/70"
            onClick={() => setOpen(false)}
          />
          <div
            id="mobile-nav"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 flex w-[min(20rem,88vw)] flex-col border-r border-line bg-secondary px-3 py-5 shadow-card"
          >
            <Brand />
            <div className="min-h-0 flex-1 overflow-y-auto">
              <NavLinks onNavigate={() => setOpen(false)} />
            </div>
          </div>
        </div>
      ) : null}

      <aside className="hidden w-64 shrink-0 border-r border-line bg-secondary/90 lg:block">
        <div className="sticky top-0 flex h-screen flex-col px-3 py-5">
          <Brand />
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <NavLinks />
          </div>
        </div>
      </aside>
    </>
  );
}
