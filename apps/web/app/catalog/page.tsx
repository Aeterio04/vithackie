"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRuns } from "@/lib/api/hooks";
import { useUiStore } from "@/lib/store/uiStore";
import { Chip } from "@/components/ui/Chip";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { extractHostname, formatRelativeTime } from "@/lib/utils";
import { ListChecks, ArrowRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";

export default function CatalogIndexPage() {
  const router = useRouter();
  const { setSelectedRunId } = useUiStore();
  const { data: runs, isLoading } = useRuns();

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);
    router.push(`/catalog/${runId}`);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-normal text-[#141413]">
            Select a Test Run for Catalog Review
          </h1>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Choose an active or completed test run to inspect planned tests,
            review gates, and the application map.
          </p>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={() => router.push("/")}
          className="gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New test run</span>
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : !runs || runs.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No test runs found"
          description="Start a test from the dashboard to generate an autonomous test catalog."
          action={
            <Button
              variant="primary"
              size="sm"
              onClick={() => router.push("/")}
            >
              Start a test run
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {runs.map((r) => (
            <div
              key={r.id}
              onClick={() => handleSelectRun(r.id)}
              className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs hover:border-[#D97757] transition-all cursor-pointer flex flex-col justify-between group"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-semibold text-[#141413] group-hover:text-[#D97757] transition-colors truncate">
                    {extractHostname(r.target_url)}
                  </span>
                  <Chip variant={r.status} size="xs">
                    {r.status}
                  </Chip>
                </div>

                {r.prompt && (
                  <p className="text-xs text-[#6B6A64] line-clamp-2">
                    {r.prompt}
                  </p>
                )}
              </div>

              <div className="pt-4 mt-3 border-t border-[#E3DACC]/60 flex items-center justify-between text-[11px] text-[#8A887F]">
                <span className="font-mono">ID: {r.id.slice(0, 8)}</span>
                <span className="flex items-center gap-1 text-[#D97757] font-medium group-hover:underline">
                  <span>Open catalog</span>
                  <ArrowRight className="w-3 h-3" />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
