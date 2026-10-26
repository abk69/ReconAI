import type { ReactNode } from "react";

import { SessionGate } from "@/components/auth/session-gate";
import { Header } from "@/components/layout/header";
import { Sidebar } from "@/components/navigation/sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:flex">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <Header />
        <main className="px-4 py-6 sm:px-6 lg:px-8">
          <SessionGate>{children}</SessionGate>
        </main>
      </div>
    </div>
  );
}
