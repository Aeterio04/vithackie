"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/lib/store/uiStore";
import { useHealth, useAuthMe, useLogout, useRuns } from "@/lib/api/hooks";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/Tooltip";
import {
  Shield,
  LayoutDashboard,
  PlusCircle,
  ListChecks,
  PlayCircle,
  Bug,
  FileBarChart2,
  LogOut,
  User,
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  const { selectedRunId } = useUiStore();
  const { data: health } = useHealth();
  const { data: user } = useAuthMe();
  const { mutate: logout, isPending: isLoggingOut } = useLogout();
  const { data: runs } = useRuns();

  // If selectedRunId is not set, use most recent run id if available
  const activeRunId = selectedRunId || (runs && runs.length > 0 ? runs[0].id : null);

  const navItems = [
    {
      label: "Dashboard",
      href: "/",
      icon: LayoutDashboard,
      isActive: pathname === "/",
    },
    {
      label: "Upload and start",
      href: "/start",
      icon: PlusCircle,
      isActive: pathname === "/start",
    },
    {
      label: "Test catalog",
      href: activeRunId ? `/catalog/${activeRunId}` : "/catalog",
      icon: ListChecks,
      isActive: pathname.startsWith("/catalog"),
    },
    {
      label: "Execution",
      href: activeRunId ? `/execution/${activeRunId}` : "/execution",
      icon: PlayCircle,
      isActive: pathname.startsWith("/execution"),
    },
    {
      label: "Results",
      href: activeRunId ? `/results/${activeRunId}` : "/results",
      icon: Bug,
      isActive: pathname.startsWith("/results"),
    },
    {
      label: "Reports",
      href: activeRunId ? `/reports/${activeRunId}` : "/reports",
      icon: FileBarChart2,
      isActive: pathname.startsWith("/reports"),
    },
  ];

  const healthStatus = health?.status || "offline";
  let healthDotColor = "bg-[#8A887F]";
  if (healthStatus === "active") healthDotColor = "bg-[#5E8C61]";
  if (healthStatus === "degraded") healthDotColor = "bg-[#D4A02A]";
  if (healthStatus === "offline") healthDotColor = "bg-[#C4473A]";

  return (
    <aside className="w-[240px] shrink-0 min-h-screen bg-[#F0EEE6] border-r border-[#E3DACC] flex flex-col justify-between p-4 select-none">
      {/* Top Section */}
      <div className="space-y-6">
        {/* Logo & Wordmark */}
        <Link href="/" className="flex items-center gap-2.5 px-2 py-1 group">
          <div className="w-8 h-8 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#D97757] shadow-xs group-hover:border-[#D97757] transition-colors">
            <Shield className="w-5 h-5 fill-[#D97757]/15 stroke-[1.75]" />
          </div>
          <div>
            <h1 className="font-heading text-xl font-normal tracking-tight text-[#141413]">
              KAWACH
            </h1>
            <p className="text-[10px] uppercase font-mono text-[#8A887F] tracking-wider -mt-1">
              AI QA Prover
            </p>
          </div>
        </Link>

        {/* Navigation */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.label}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-all cursor-pointer",
                  item.isActive
                    ? "bg-white text-[#141413] shadow-xs border border-[#E3DACC]/60 font-semibold"
                    : "text-[#6B6A64] hover:text-[#141413] hover:bg-[#E9E6DC]/60"
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4 stroke-[1.5]",
                    item.isActive ? "text-[#D97757]" : "text-[#8A887F]"
                  )}
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Bottom Section */}
      <div className="pt-4 border-t border-[#E3DACC]/80 space-y-3">
        {/* Sandbox Health Status */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-[#FAF9F5]/70 border border-[#E3DACC]/70 text-[11px] cursor-help">
                <span className="text-[#6B6A64] font-medium">Sandbox Workers</span>
                <div className="flex items-center gap-1.5 font-mono">
                  <span className={cn("w-2 h-2 rounded-full", healthDotColor)} />
                  <span className="capitalize text-[#141413]">
                    {healthStatus}
                  </span>
                </div>
              </div>
            </TooltipTrigger>
            <TooltipContent side="right">
              <p className="font-semibold mb-1">Sandbox Environment</p>
              <p>Status: {healthStatus}</p>
              <p>Workers up: {health?.workers_up ?? "-"}</p>
              <p>Queue depth: {health?.queue_depth ?? "-"}</p>
              <p className="text-[10px] text-[#A8A59B] mt-1">Polled every 30s</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* User Info & Logout */}
        <div className="flex items-center justify-between px-2 pt-1">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-full bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#D97757] text-xs font-semibold shrink-0">
              {user?.username ? (
                user.username.slice(0, 2).toUpperCase()
              ) : (
                <User className="w-3.5 h-3.5 text-[#8A887F]" />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-[#141413] truncate">
                {user?.name || user?.username || "Authenticated"}
              </p>
              <p className="text-[10px] text-[#8A887F] truncate">
                {user?.role || "QA Engineer"}
              </p>
            </div>
          </div>

          <button
            onClick={() => logout()}
            disabled={isLoggingOut}
            title="Log out"
            className="text-[#8A887F] hover:text-[#C4473A] p-1.5 rounded-lg hover:bg-[#FAEBE9] transition-colors cursor-pointer"
          >
            <LogOut className="w-4 h-4 stroke-[1.5]" />
          </button>
        </div>
      </div>
    </aside>
  );
}
