"use client";

import React, { useMemo } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useUiStore } from "@/lib/store/uiStore";
import { useRun, useRuns } from "@/lib/api/hooks";
import { RunSwitcher } from "@/components/ui/RunSwitcher";
import { Button } from "@/components/ui/Button";
import { extractHostname } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/DropdownMenu";
import { Bell, ShieldCheck, Plus, AlertCircle, Clock } from "lucide-react";

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

  // Compute page title and subtitle if not provided
  const pageMeta = useMemo(() => {
    if (title) return { title, subtitle };

    if (pathname === "/") {
      return {
        title: "Test Operations",
        subtitle: "Deterministic QA pipelines backed by replay proof",
      };
    }
    if (pathname === "/start") {
      return {
        title: "Upload & Start Test Run",
        subtitle: "Specify application target, scope, and test credentials",
      };
    }
    if (pathname.startsWith("/catalog")) {
      return {
        title: "Test Catalog & Review Gate",
        subtitle: "Human and autonomous test plan validation",
      };
    }
    if (pathname.startsWith("/execution")) {
      return {
        title: "Live Execution & Evidence",
        subtitle: "Parallel Playwright workers & deterministic verifier",
      };
    }
    if (pathname.startsWith("/results")) {
      return {
        title: "Verified Findings & Bugs",
        subtitle: "Bugs proved with 3x replay trials and artifacts",
      };
    }
    if (pathname.startsWith("/reports")) {
      return {
        title: "Evidence-Backed QA Report",
        subtitle: "Deterministic funnel, spec coverage, and reusable tests",
      };
    }
    return {
      title: "KAWACH",
      subtitle: "Autonomous QA Testing Agent",
    };
  }, [pathname, title, subtitle]);

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
    <header className="h-16 px-8 border-b border-[#E3DACC] bg-[#FAF9F5] flex items-center justify-between select-none shrink-0">
      {/* Title & Subtitle */}
      <div className="flex items-center gap-6">
        <div>
          <h2 className="font-heading text-lg font-normal text-[#141413]">
            {pageMeta.title}
          </h2>
          {pageMeta.subtitle && (
            <p className="text-xs text-[#6B6A64] -mt-0.5">
              {pageMeta.subtitle}
            </p>
          )}
        </div>

        {/* Authorized Host Badge */}
        {targetHost ? (
          <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#EBF2EB] border border-[#D2E3D3] text-[#47704A] text-[11px] font-medium font-mono">
            <ShieldCheck className="w-3.5 h-3.5 text-[#5E8C61]" />
            <span>Authorized: {targetHost}</span>
          </div>
        ) : (
          <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#F0EEE6] border border-[#E3DACC] text-[#8A887F] text-[11px] font-medium">
            <ShieldCheck className="w-3.5 h-3.5 text-[#8A887F]" />
            <span>Authorized staging/local</span>
          </div>
        )}
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3">
        {/* Run Switcher Dropdown */}
        <RunSwitcher />

        {/* Notification Bell */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="relative p-2 rounded-xl text-[#6B6A64] hover:text-[#141413] hover:bg-[#F0EEE6] transition-colors border border-[#E3DACC] bg-white shadow-xs cursor-pointer"
              title="Notifications"
            >
              <Bell className="w-4 h-4 stroke-[1.5]" />
              {notifications.length > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#D97757] text-white text-[10px] font-bold flex items-center justify-center">
                  {notifications.length}
                </span>
              )}
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent className="w-80 p-2">
            <div className="px-2 py-1.5 text-xs font-semibold text-[#141413]">
              Notifications ({notifications.length})
            </div>
            <DropdownMenuSeparator />

            {notifications.length === 0 ? (
              <div className="py-6 text-center text-xs text-[#8A887F] italic">
                All runs operating smoothly. No pending alerts.
              </div>
            ) : (
              notifications.map((n) => (
                <DropdownMenuItem
                  key={n.id}
                  onClick={() => router.push(`/execution/${n.runId}`)}
                  className="flex items-start gap-2.5 py-2.5"
                >
                  <div className="mt-0.5">
                    {n.type === "review" ? (
                      <Clock className="w-4 h-4 text-[#D97757]" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-[#C4473A]" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-[#141413]">
                      {n.title}
                    </p>
                    <p className="text-[11px] text-[#6B6A64] mt-0.5 leading-snug">
                      {n.message}
                    </p>
                  </div>
                </DropdownMenuItem>
              ))
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Primary CTA: New test run */}
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            router.push("/");
            // Focus URL input if already on dashboard
            const input = document.getElementById("target-url-input");
            if (input) input.focus();
          }}
          className="gap-1.5"
        >
          <Plus className="w-4 h-4 stroke-[2]" />
          <span>New test run</span>
        </Button>
      </div>
    </header>
  );
}
