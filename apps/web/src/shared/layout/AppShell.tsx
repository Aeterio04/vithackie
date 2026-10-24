"use client";

import React, { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useUiStore } from "@/lib/store/uiStore";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthPage = pathname.startsWith("/login");
  const { resetUIState } = useUiStore();

  // Clear UI state on app initialization to prevent displaying stale run data after restart
  useEffect(() => {
    resetUIState();
  }, [resetUIState]);

  if (isAuthPage) {
    return <main className="min-h-screen bg-[#FAF9F5]">{children}</main>;
  }

  return (
    <div className="flex min-h-screen bg-[#FAF9F5] text-[#141413]">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 p-8 overflow-y-auto max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
