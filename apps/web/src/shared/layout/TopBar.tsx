"use client";

import React, { useMemo } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useUiStore } from "@/lib/store/uiStore";
import { useRun, useRuns } from "@/lib/api/hooks";
import { RunSwitcher } from "@/components/ui/RunSwitcher";
import { extractHostname } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/DropdownMenu";
import { Bell, AlertCircle, Clock } from "lucide-react";

interface TopBarProps {
  title?: string;
  subtitle?: string;
}

export function TopBar({ title, subtitle }: TopBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { selectedRunId } = useUiStore();
  const { data: currentRun } = useRun(selectedRunId);
  const { data: runs } = useRuns();

  // Derive clean breadcrumb ("Test Operations / New test run")
  const breadcrumb = useMemo(() => {
    let section = "New test run";

    if (pathname === "/" || pathname.startsWith("/start")) {
      section = "New test run";
    } else if (pathname.startsWith("/catalog")) {
      section = "Test Catalog";
    } else if (pathname.startsWith("/execution")) {
      section = "Live Execution";
    } else if (pathname.startsWith("/results")) {
      section = "Verified Findings";
    } else if (pathname.startsWith("/reports")) {
      section = "QA Report";
    } else if (pathname.startsWith("/projects")) {
      section = "Projects";
    }

    return {
      category: "Test Operations",
      section: title || section,
    };
  }, [pathname, title]);

  // Derive notifications from runs
  const notifications = useMemo(() => {
    if (!runs) return [];
    const alerts: Array<{
      id: string;
      runId: string;
      title: string;
      message: string;
      type: "review" | "error" | "budget";
    }> = [];

    runs.forEach((r) => {
      if (r.status === "awaiting_review") {
        alerts.push({
          id: `review-${r.id}`,
          runId: r.id,
          title: "Awaiting Review",
          message: `${extractHostname(r.target_url)} has tests awaiting your approval`,
          type: "review",
        });
      } else if (r.status === "failed") {
        alerts.push({
          id: `fail-${r.id}`,
          runId: r.id,
          title: "Run Failed",
          message: `${extractHostname(r.target_url)} encountered an error`,
          type: "error",
        });
      } else if (r.status === "budget_exhausted") {
        alerts.push({
          id: `budget-${r.id}`,
          runId: r.id,
          title: "Budget Exhausted",
          message: `${extractHostname(r.target_url)} exceeded page or time budget`,
          type: "budget",
        });
      }
    });

    return alerts;
  }, [runs]);

  const targetHost = currentRun?.target_url
    ? extractHostname(currentRun.target_url)
    : null;

  return (
    <header className="h-16 px-8 border-b border-stone-200 bg-[#FAF9F5]/90 backdrop-blur-sm sticky top-0 z-30 flex items-center justify-between select-none shrink-0">
      {/* Left: Active Section Title */}
      <div className="flex items-center text-sm min-w-0">
        <span className="text-[#3D3929] font-medium truncate text-[15px]">
          {breadcrumb.section}
        </span>
      </div>

      {/* Right Controls: dropdown, bell */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {/* Run Switcher Dropdown */}
        <RunSwitcher />

        {/* Notification Bell */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="relative h-9 w-9 rounded-lg border border-stone-200 bg-[#FAF9F5] hover:bg-[#EDEAE0] flex items-center justify-center text-[#6B6A5E] hover:text-[#3D3929] transition-colors duration-150 cursor-pointer shadow-none"
              title="Notifications"
            >
              <Bell className="w-[18px] h-[18px] stroke-[1.5]" />
              {notifications.length > 0 && (
                <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-[#C6613F]" />
              )}
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent className="w-80 p-2 bg-[#FAF9F5] border border-stone-200 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
            <div className="px-2 py-1.5 text-[12px] font-medium text-[#3D3929]">
              Notifications ({notifications.length})
            </div>
            <DropdownMenuSeparator className="bg-stone-200" />

            {notifications.length === 0 ? (
              <div className="py-6 text-center text-[12px] text-[#6B6A5E] italic">
                All runs operating smoothly. No pending alerts.
              </div>
            ) : (
              notifications.map((n) => (
                <DropdownMenuItem
                  key={n.id}
                  onClick={() => router.push(`/execution/${n.runId}`)}
                  className="flex items-start gap-2.5 py-2 px-2 rounded-lg hover:bg-[#EDEAE0] text-[#3D3929] transition-colors duration-150"
                >
                  <div className="mt-0.5 shrink-0">
                    {n.type === "review" ? (
                      <Clock className="w-4 h-4 text-[#C6613F]" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-[#B5552F]" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-[#3D3929] leading-tight">
                      {n.title}
                    </p>
                    <p className="text-[11px] text-[#6B6A5E] mt-0.5 leading-snug">
                      {n.message}
                    </p>
                  </div>
                </DropdownMenuItem>
              ))
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
