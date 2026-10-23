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

  // Derive active states from current pathname
  const isStartPage =
    pathname === "/start" ||
    pathname.startsWith("/start/") ||
    pathname === "/projects/new";

  const isDashboardPage = pathname === "/" && !isStartPage;

  const navItems = [
    {
      label: "Dashboard",
      href: "/",
      icon: LayoutDashboard,
      isActive: isDashboardPage,
    },
    {
      label: "Upload and start",
      href: "/start",
      icon: PlusCircle,
      isActive: isStartPage,
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
    <aside className="w-[260px] shrink-0 h-screen sticky top-0 bg-[#F5F4ED] border-r border-stone-200 flex flex-col justify-between select-none">
      {/* Top Fixed Section: exactly h-16 with border-b to align with the header level */}
      <div className="h-16 border-b border-stone-200 flex items-center justify-center text-center shrink-0 px-4">
        <Link
          href="/"
          className="inline-block hover:opacity-80 transition-opacity duration-150"
        >
          <span
            className="text-[42px] text-[#3D3929] leading-none select-none tracking-normal font-normal block text-center"
            style={{ fontFamily: "'Billabong', 'Cookie', 'Grand Hotel', 'Brush Script MT', cursive" }}
          >
            Kawach
          </span>
        </Link>
      </div>

      {/* Middle Scrollable Navigation Section */}
      <div className="flex-1 overflow-y-auto p-3 space-y-0.5" style={{ scrollbarWidth: "thin" }}>
        <div className="px-3 text-[12px] font-medium text-[#6B6A5E] mt-1 mb-1.5">
          Navigation
        </div>

        <nav className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.label}
                href={item.href}
                className={cn(
                  "flex items-center gap-[10px] px-3 py-2 rounded-lg text-[14px] leading-5 transition-colors duration-150 cursor-pointer w-full text-left",
                  item.isActive
                    ? "bg-[#E8E4D8] text-[#3D3929] font-medium"
                    : "text-[#3D3929] hover:bg-[#EDEAE0]"
                )}
              >
                <Icon
                  className={cn(
                    "w-[18px] h-[18px] stroke-[1.5] shrink-0",
                    item.isActive ? "text-[#C6613F]" : "text-[#6B6A5E]"
                  )}
                />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Bottom Pinned Footer Section */}
      <div className="p-3 mt-auto border-t border-stone-200 space-y-2.5 shrink-0">
        {/* Sandbox Health Status */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-[#FAF9F5] border border-[#E5E2D6] text-[12px] cursor-help">
                <span className="text-[#6B6A5E] font-normal">Sandbox workers</span>
                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                  <span className={cn("w-2 h-2 rounded-full", healthDotColor)} />
                  <span className="capitalize text-[#3D3929]">
                    {healthStatus}
                  </span>
                </div>
              </div>
            </TooltipTrigger>
            <TooltipContent
              side="right"
              className="bg-[#FAF9F5] border border-[#E5E2D6] text-[#3D3929] rounded-lg p-2.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] text-xs"
            >
              <p className="font-medium text-[#3D3929] mb-1">Sandbox Environment</p>
              <p className="text-[#6B6A5E]">Status: {healthStatus}</p>
              <p className="text-[#6B6A5E]">Workers up: {health?.workers_up ?? "-"}</p>
              <p className="text-[#6B6A5E]">Queue depth: {health?.queue_depth ?? "-"}</p>
              <p className="text-[10px] text-[#8A887F] mt-1">Polled every 30s</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* User Info & Logout */}
        <div className="flex items-center justify-between px-2 pt-0.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-full bg-[#E8E4D8] border border-[#E5E2D6] flex items-center justify-center text-[#3D3929] text-[12px] font-medium shrink-0">
              {user?.username ? (
                user.username.slice(0, 2).toUpperCase()
              ) : (
                <User className="w-3.5 h-3.5 text-[#6B6A5E]" />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-[14px] font-medium text-[#3D3929] truncate leading-tight">
                {user?.name || user?.username || "Authenticated"}
              </p>
              <p className="text-[12px] text-[#6B6A5E] truncate leading-tight mt-0.5">
                {user?.role || "QA Engineer"}
              </p>
            </div>
          </div>

          <button
            onClick={() => logout()}
            disabled={isLoggingOut}
            title="Log out"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#6B6A5E] hover:text-[#C6613F] hover:bg-[#EDEAE0] transition-colors duration-150 cursor-pointer"
          >
            <LogOut className="w-[18px] h-[18px] stroke-[1.5]" />
          </button>
        </div>
      </div>
    </aside>
  );
}
