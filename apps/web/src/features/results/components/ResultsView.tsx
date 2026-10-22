"use client";

import React, { useState, useMemo, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useRun, useBugs, useTests } from "@/lib/api/hooks";
import { useUiStore } from "@/lib/store/uiStore";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Drawer } from "@/components/ui/Drawer";
import { ReplayPips } from "@/components/ui/ReplayPips";
import { type Bug } from "@/types";
import { extractHostname, formatDuration } from "@/lib/utils";
import {
  Bug as BugIcon,
  CheckCircle2,
  Search,
  ExternalLink,
  Camera,
  Video,
  FileCode,
  FileSearch,
  ArrowRight,
  FileBarChart2,
} from "lucide-react";

export function ResultsView() {
  const params = useParams();
  const runId = params.runId as string;
  const router = useRouter();
  const { setSelectedRunId } = useUiStore();

  useEffect(() => {
    if (runId) setSelectedRunId(runId);
  }, [runId, setSelectedRunId]);

  const { data: run } = useRun(runId);
  const { data: bugs, isLoading: isBugsLoading } = useBugs(runId);
  const { data: tests, isLoading: isTestsLoading } = useTests(runId);

  // States
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [previewBug, setPreviewBug] = useState<Bug | null>(null);

  // Status counts
  const counts = useMemo(() => {
    const list = bugs || [];
    return {
      all: list.length,
      confirmed: list.filter((b) => b.status === "confirmed").length,
      flaky: list.filter((b) => b.status === "flaky").length,
      not_reproduced: list.filter((b) => b.status === "not_reproduced").length,
      suspected: list.filter((b) => b.status === "suspected" || b.status === "verifying").length,
    };
  }, [bugs]);

  // Filtered bugs
  const filteredBugs = useMemo(() => {
    if (!bugs) return [];
    return bugs.filter((bug) => {
      const matchesSearch =
        bug.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        bug.spec_item_ids.some((id) =>
          id.toLowerCase().includes(searchQuery.toLowerCase())
        );

      let matchesStatus = true;
      if (statusFilter === "confirmed") matchesStatus = bug.status === "confirmed";
      else if (statusFilter === "flaky") matchesStatus = bug.status === "flaky";
      else if (statusFilter === "not_reproduced")
        matchesStatus = bug.status === "not_reproduced";
      else if (statusFilter === "suspected")
        matchesStatus = bug.status === "suspected" || bug.status === "verifying";

      const matchesSeverity =
        severityFilter === "all" || bug.severity === severityFilter;
      const matchesSource =
        sourceFilter === "all" || bug.source === sourceFilter;

      return matchesSearch && matchesStatus && matchesSeverity && matchesSource;
    });
  }, [bugs, searchQuery, statusFilter, severityFilter, sourceFilter]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Run Header */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-heading text-2xl font-normal text-[#141413]">
              {run ? extractHostname(run.target_url) : "Loading..."}
            </h1>
            <Chip variant={run?.status || "neutral"} size="sm">
              {run?.status || "loading"}
            </Chip>
          </div>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Verified findings and test results backed by 3x deterministic replay
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push(`/execution/${runId}`)}
          >
            Live Execution
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => router.push(`/reports/${runId}`)}
            className="gap-1.5"
          >
            <FileBarChart2 className="w-3.5 h-3.5" />
            <span>Generate Report</span>
          </Button>
        </div>
      </div>

      {/* Tabs: Bugs & Tests */}
      <Tabs defaultValue="bugs" className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="bugs" className="gap-1.5">
            <BugIcon className="w-4 h-4" />
            <span>Verified Bugs ({bugs?.length ?? 0})</span>
          </TabsTrigger>
          <TabsTrigger value="tests" className="gap-1.5">
            <CheckCircle2 className="w-4 h-4" />
            <span>All Tests ({tests?.length ?? 0})</span>
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: BUGS */}
        <TabsContent value="bugs" className="space-y-4">
          {/* Status Filter Chips with Counts */}
          <div className="flex flex-wrap items-center gap-2">
            {[
              { id: "all", label: "All Findings", count: counts.all },
              { id: "confirmed", label: "Confirmed (3/3)", count: counts.confirmed },
              { id: "flaky", label: "Flaky (1-2/3)", count: counts.flaky },
              { id: "not_reproduced", label: "Not Reproduced (0/3)", count: counts.not_reproduced },
              { id: "suspected", label: "Suspected", count: counts.suspected },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setStatusFilter(f.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all border cursor-pointer flex items-center gap-1.5 ${
                  statusFilter === f.id
                    ? "bg-[#D97757] text-white border-[#D97757] shadow-xs"
                    : "bg-white text-[#6B6A64] border-[#E3DACC] hover:bg-[#FAF9F5]"
                }`}
              >
                <span>{f.label}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                    statusFilter === f.id
                      ? "bg-white/20 text-white"
                      : "bg-[#F0EEE6] text-[#8A887F]"
                  }`}
                >
                  {f.count}
                </span>
              </button>
            ))}
          </div>

          {/* Search & Secondary Filters */}
          <div className="bg-white border border-[#E3DACC] rounded-xl p-3 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-xs">
            <div className="relative flex-1 max-w-sm">
              <Search className="w-4 h-4 text-[#8A887F] absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search bugs by title, spec item..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] focus:outline-none focus:ring-1 focus:ring-[#D97757]"
              />
            </div>

            <div className="flex items-center gap-2 text-xs">
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="px-2.5 py-1.5 bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] text-xs focus:outline-none"
              >
                <option value="all">All Severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>

              <select
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
                className="px-2.5 py-1.5 bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] text-xs focus:outline-none"
              >
                <option value="all">All Sources</option>
                <option value="test_runner">Test Runner</option>
                <option value="exploratory">Exploratory</option>
              </select>
            </div>
          </div>

          {/* Bugs Table */}
          {isBugsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : filteredBugs.length === 0 ? (
            <EmptyState
              icon={BugIcon}
              title="No bugs match criteria"
              description="No findings matched the selected status or severity filters."
            />
          ) : (
            <div className="bg-white border border-[#E3DACC] rounded-[16px] overflow-hidden shadow-xs">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-[#FAF9F5] border-b border-[#E3DACC] text-[#6B6A64]">
                    <th className="py-3 px-4 font-semibold">Severity & Status</th>
                    <th className="py-3 px-4 font-semibold">Bug Title</th>
                    <th className="py-3 px-4 font-semibold">Source</th>
                    <th className="py-3 px-4 font-semibold">Deterministic Replay</th>
                    <th className="py-3 px-4 font-semibold">Evidence</th>
                    <th className="py-3 px-4 font-semibold text-right">Action</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-[#E3DACC]/60">
                  {filteredBugs.map((bug) => (
                    <tr
                      key={bug.id}
                      onClick={() => setPreviewBug(bug)}
                      className="hover:bg-[#FAF9F5]/70 transition-colors cursor-pointer group"
                    >
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <Chip variant={bug.severity} size="xs">
                            {bug.severity}
                          </Chip>
                          <Chip variant={bug.status} size="xs">
                            {bug.status}
                          </Chip>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 min-w-[260px]">
                        <p className="font-medium text-[#141413] group-hover:text-[#D97757] transition-colors text-sm">
                          {bug.title}
                        </p>
                        {bug.spec_item_ids.length > 0 && (
                          <div className="flex items-center gap-1 mt-1">
                            {bug.spec_item_ids.map((id) => (
                              <span
                                key={id}
                                className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-[#F0EEE6] text-[#6B6A64] border border-[#E3DACC]"
                              >
                                {id}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>

                      <td className="py-3.5 px-4 text-[#6B6A64] capitalize">
                        {bug.source === "test_runner"
                          ? "Test Runner"
                          : "Exploratory"}
                      </td>

                      <td className="py-3.5 px-4">
                        <ReplayPips
                          replays={bug.replays}
                          status={bug.status}
                          bug={bug}
                          size="md"
                        />
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2 text-[#8A887F]">
                          {bug.evidence?.screenshots &&
                            bug.evidence.screenshots.length > 0 && (
                              <span title={`${bug.evidence.screenshots.length} Screenshots`}>
                                <Camera className="w-4 h-4 text-[#6B6A64]" />
                              </span>
                            )}
                          {bug.evidence?.video_url && (
                            <span title="Video playback">
                              <Video className="w-4 h-4 text-[#6B6A64]" />
                            </span>
                          )}
                          {bug.evidence?.trace_url && (
                            <span title="Playwright trace archive">
                              <FileSearch className="w-4 h-4 text-[#6B6A64]" />
                            </span>
                          )}
                          {bug.repro_script_url && (
                            <span title="Deterministic Playwright .ts repro script">
                              <FileCode className="w-4 h-4 text-[#D97757]" />
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/results/${runId}/bugs/${bug.id}`);
                          }}
                          className="text-xs text-[#D97757] hover:underline font-medium inline-flex items-center gap-1 cursor-pointer"
                        >
                          <span>Full view</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        {/* TAB 2: TESTS */}
        <TabsContent value="tests">
          <div className="bg-white border border-[#E3DACC] rounded-[16px] overflow-hidden shadow-xs">
            {isTestsLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : !tests || tests.length === 0 ? (
              <EmptyState
                icon={CheckCircle2}
                title="No tests recorded"
                description="Test executions will be shown here as they complete."
                className="py-12"
              />
            ) : (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-[#FAF9F5] border-b border-[#E3DACC] text-[#6B6A64]">
                    <th className="py-3 px-4 font-semibold">Test Title</th>
                    <th className="py-3 px-4 font-semibold">Status</th>
                    <th className="py-3 px-4 font-semibold">Duration</th>
                    <th className="py-3 px-4 font-semibold">Worker</th>
                    <th className="py-3 px-4 font-semibold">Error Message</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-[#E3DACC]/60">
                  {tests.map((t) => (
                    <tr key={t.id} className="hover:bg-[#FAF9F5] transition-colors">
                      <td className="py-3 px-4 font-medium text-[#141413]">
                        {t.title}
                      </td>

                      <td className="py-3 px-4">
                        <Chip variant={t.status} size="xs" dot>
                          {t.status}
                        </Chip>
                      </td>

                      <td className="py-3 px-4 font-mono text-[#6B6A64]">
                        {formatDuration(t.duration_ms)}
                      </td>

                      <td className="py-3 px-4 font-mono text-[#8A887F]">
                        {t.worker_id || "-"}
                      </td>

                      <td className="py-3 px-4 font-mono text-[#C4473A] max-w-xs truncate">
                        {t.error_message || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* QUICK PREVIEW DRAWER */}
      <Drawer
        isOpen={Boolean(previewBug)}
        onClose={() => setPreviewBug(null)}
        title={previewBug?.title || "Bug Preview"}
        subtitle={`Bug ID: ${previewBug?.id || ""}`}
        footer={
          <Button
            variant="primary"
            size="md"
            onClick={() => {
              if (previewBug) {
                router.push(`/results/${runId}/bugs/${previewBug.id}`);
              }
            }}
            className="w-full gap-2"
          >
            <span>Open Full Evidence & Replay View</span>
            <ArrowRight className="w-4 h-4" />
          </Button>
        }
      >
        {previewBug && (
          <div className="space-y-5">
            {/* Verdict Card */}
            <div className="p-4 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[#141413]">
                  Deterministic Replay Verdict
                </span>
                <ReplayPips
                  replays={previewBug.replays}
                  status={previewBug.status}
                  bug={previewBug}
                  size="md"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <Chip variant={previewBug.status} size="sm">
                  {previewBug.status}
                </Chip>
                <Chip variant={previewBug.severity} size="sm">
                  {previewBug.severity}
                </Chip>
              </div>
            </div>

            {/* Expected vs Actual */}
            <div className="space-y-3 text-xs">
              <div>
                <span className="font-semibold text-[#141413] block mb-1">
                  Expected Result
                </span>
                <p className="bg-[#FAF9F5] p-2.5 rounded-lg border border-[#E3DACC] text-[#6B6A64]">
                  {previewBug.expected || "Expected behavior according to spec"}
                </p>
              </div>

              <div>
                <span className="font-semibold text-[#141413] block mb-1">
                  Actual Behavior (Observed)
                </span>
                <p className="bg-[#FAF9F5] p-2.5 rounded-lg border border-[#E3DACC] text-[#C4473A]">
                  {previewBug.actual || "Bug occurred during Playwright replay"}
                </p>
              </div>
            </div>

            {/* Steps to Reproduce */}
            {previewBug.steps_to_reproduce &&
              previewBug.steps_to_reproduce.length > 0 && (
                <div className="space-y-1.5">
                  <span className="text-xs font-semibold text-[#141413]">
                    Steps to Reproduce
                  </span>
                  <ol className="list-decimal list-inside text-xs space-y-1 text-[#6B6A64] bg-[#FAF9F5] p-3 rounded-xl border border-[#E3DACC]">
                    {previewBug.steps_to_reproduce.map((step, idx) => (
                      <li key={idx} className="leading-relaxed">
                        {step}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

            {/* Screenshot Evidence Artifact */}
            {previewBug.evidence?.screenshots &&
              previewBug.evidence.screenshots.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <span className="text-xs font-semibold text-[#141413] block">
                    Evidence Screenshot Artifact
                  </span>
                  <a
                    href={previewBug.evidence.screenshots[0]}
                    target="_blank"
                    rel="noreferrer"
                    className="group relative block w-full aspect-video rounded-xl overflow-hidden border border-[#E3DACC] bg-[#1E1E1C] shadow-2xs hover:border-[#D97757] transition-all"
                  >
                    <img
                      src={previewBug.evidence.screenshots[0]}
                      alt="Bug evidence screenshot"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      loading="lazy"
                    />
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs gap-1.5 font-medium">
                      <span>Click to open full artifact</span>
                    </div>
                  </a>
                </div>
              )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
