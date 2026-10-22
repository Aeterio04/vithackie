"use client";

import React from "react";
import { useRouter, usePathname } from "next/navigation";
import { useRuns, useRun } from "@/lib/api/hooks";
import { useUiStore } from "@/lib/store/uiStore";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "./DropdownMenu";
import { Chip } from "./Chip";
import { extractHostname } from "@/lib/utils";
import { ChevronDown, Layers, Plus } from "lucide-react";

export function RunSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const { selectedRunId, setSelectedRunId } = useUiStore();
  const { data: runs, isLoading } = useRuns();
  const { data: currentRun } = useRun(selectedRunId);

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);

    // If current path has a runId segment (e.g. /execution/run-123 or /results/run-123)
    // replace it with the new runId
    const segments = pathname.split("/");
    const scopeRoutes = ["catalog", "execution", "results", "reports"];

    if (segments.length >= 3 && scopeRoutes.includes(segments[1])) {
      segments[2] = runId;
      router.push(segments.join("/"));
    } else if (segments.length === 2 && scopeRoutes.includes(segments[1])) {
      router.push(`/${segments[1]}/${runId}`);
    }
  };

  const selectedDisplay = currentRun
    ? `${extractHostname(currentRun.target_url)} (#${currentRun.id.slice(0, 8)})`
    : selectedRunId
    ? `Run #${selectedRunId.slice(0, 8)}`
    : "Select active run...";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-[#141413] bg-white border border-[#E3DACC] rounded-xl hover:bg-[#FAF9F5] transition-colors focus-visible:ring-2 focus-visible:ring-[#D97757] shadow-xs cursor-pointer max-w-[280px]"
          title="Switch active test run"
        >
          <Layers className="w-3.5 h-3.5 text-[#D97757] shrink-0" />
          <span className="truncate">{selectedDisplay}</span>
          <ChevronDown className="w-3.5 h-3.5 text-[#8A887F] shrink-0 ml-auto" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="w-72 max-h-80 overflow-y-auto">
        <div className="px-2 py-1.5 text-[11px] font-semibold text-[#8A887F] uppercase tracking-wider">
          Active & Recent Runs
        </div>

        {isLoading ? (
          <div className="px-3 py-2 text-xs text-[#8A887F]">Loading runs...</div>
        ) : !runs || runs.length === 0 ? (
          <div className="px-3 py-3 text-xs text-[#8A887F] text-center italic">
            No test runs yet
          </div>
        ) : (
          runs.map((r) => (
            <DropdownMenuItem
              key={r.id}
              onClick={() => handleSelectRun(r.id)}
              className="flex items-center justify-between gap-2 py-2"
            >
              <div className="min-w-0">
                <p className="font-medium text-[#141413] truncate text-xs">
                  {extractHostname(r.target_url)}
                </p>
                <p className="text-[10px] font-mono text-[#8A887F]">
                  ID: {r.id.slice(0, 8)}
                </p>
              </div>

              <Chip variant={r.status} size="xs">
                {r.status}
              </Chip>
            </DropdownMenuItem>
          ))
        )}

        <DropdownMenuSeparator />

        <DropdownMenuItem
          onClick={() => {
            router.push("/");
          }}
          className="text-[#D97757] font-medium flex items-center gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Start new test run</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
