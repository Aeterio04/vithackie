"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { API_ENDPOINTS } from "@/lib/api/config";

export interface Alignment {
  specTcCount: number;
  catalogCount: number;
  missing: string[];
  extra: string[];
  changed: string[];
  uncoveredRequirements: string[];
  requirementCount: number;
  alignmentPercent: number;
  canStartExecution: boolean;
  blockReason: string | null;
  specHash: string;
  catalogVersion: string;
  lintFailures?: Record<string, string[]>;
}

/** Spec vs catalog alignment; 404 (run is not spec-driven) resolves to null so no banner shows. */
export function useAlignment(runId: string | null | undefined) {
  return useQuery<Alignment | null>({
    queryKey: ["runs", runId, "alignment"],
    queryFn: async () => {
      try {
        return await apiClient<Alignment>(`${API_ENDPOINTS.RUN_CATALOG(runId!).replace(/\/catalog$/, "")}/alignment`);
      } catch {
        return null;
      }
    },
    enabled: Boolean(runId),
  });
}

export function AlignmentBanner({ alignment: a }: { alignment: Alignment }) {
  const ok = a.canStartExecution;
  const lint = Object.keys(a.lintFailures ?? {}).length;
  return (
    <div
      role="status"
      className={`rounded-[16px] border p-4 text-sm ${ok ? "border-[#BFD8C4] bg-[#F1F8F2] text-[#1E4D2B]" : "border-[#E8B4B4] bg-[#FBF0F0] text-[#7A1F1F]"}`}
    >
      <div className="font-medium">
        Spec alignment {a.alignmentPercent}%: {a.catalogCount} of {a.specTcCount} spec test cases in catalog, {a.requirementCount - a.uncoveredRequirements.length} of {a.requirementCount} requirements covered
      </div>
      <div className="mt-1 text-xs font-mono opacity-80">
        spec {a.specHash.slice(0, 10)} - catalog {a.catalogVersion} - missing {a.missing.length} - extra {a.extra.length} - altered {a.changed.length} - lint failures {lint}
      </div>
      {!ok && <div className="mt-1 text-xs">Execution is blocked: {a.blockReason}</div>}
    </div>
  );
}
