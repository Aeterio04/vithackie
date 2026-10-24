"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useRuns,
  useRun,
  useStats,
  useCatalog,
  useSubmitReview,
  useBugs,
} from "@/lib/api/hooks";
import { useRunStream } from "@/hooks/useRunStream";
import { useUiStore } from "@/lib/store/uiStore";
import { StartTestForm } from "@/components/features/StartTestForm";
import { Stepper } from "@/components/ui/Stepper";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { LogViewer } from "@/components/ui/LogViewer";
import { ReplayPips } from "@/components/ui/ReplayPips";
import { BudgetMeter } from "@/components/ui/BudgetMeter";
import { Checkbox } from "@/components/ui/Checkbox";
import { useToast } from "@/components/ui/Toast";
import {
  extractHostname,
  formatRelativeTime,
  formatDateTime,
} from "@/lib/utils";
import {
  Layers,
  Bug as BugIcon,
  CheckCircle2,
  AlertTriangle,
  Clock,
  PlayCircle,
  Camera,
  Video,
  FileCode,
  FileSearch,
  ExternalLink,
  Sparkles,
  ArrowRight,
  Shield,
  Activity,
} from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();

  React.useEffect(() => {
    router.replace("/projects");
  }, [router]);

  const { toast } = useToast();
  const { setSelectedRunId } = useUiStore();

  const { data: stats, isLoading: isStatsLoading } = useStats();
  const { data: runs, isLoading: isRunsLoading } = useRuns();

  // Find the most recent active or latest run for the live column
  const activeRun = useMemo(() => {
    if (!runs || runs.length === 0) return null;
    const active = runs.find(
      (r) =>
        r.status !== "completed" &&
        r.status !== "failed" &&
        r.status !== "cancelled" &&
        r.status !== "budget_exhausted"
    );
    return active || runs[0];
  }, [runs]);

  // Connect live SSE stream to active run
  const isTerminalRun =
    activeRun?.status === "completed" ||
    activeRun?.status === "failed" ||
    activeRun?.status === "cancelled" ||
    activeRun?.status === "budget_exhausted";

  const { logs, clearLogs, connectionState } = useRunStream(
    activeRun?.id,
    isTerminalRun
  );

  // Find latest run that has "awaiting_review"
  const awaitingReviewRun = useMemo(() => {
    if (!runs) return null;
    return runs.find((r) => r.status === "awaiting_review") || activeRun;
  }, [runs, activeRun]);

  const { data: catalogTests, isLoading: isCatalogLoading } = useCatalog(
    awaitingReviewRun?.id
  );
  const pendingTests = useMemo(() => {
    return (catalogTests || []).filter((t) => t.review_status === "pending");
  }, [catalogTests]);

  const [selectedTestIds, setSelectedTestIds] = useState<string[]>([]);
  const { mutate: submitReview, isPending: isSubmittingReview } =
    useSubmitReview(awaitingReviewRun?.id || "");

  const handleApproveSelected = () => {
    if (selectedTestIds.length === 0 || !awaitingReviewRun) return;
    submitReview(
      {
        test_ids: selectedTestIds,
        decision: "approved",
        reason: "Approved from dashboard review gate",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "Tests approved",
            message: `${selectedTestIds.length} test(s) approved for execution`,
          });
          setSelectedTestIds([]);
        },
      }
    );
  };

  const handleApproveAll = () => {
    if (pendingTests.length === 0 || !awaitingReviewRun) return;
    const allIds = pendingTests.map((t) => t.id);
    submitReview(
      {
        test_ids: allIds,
        decision: "approved",
        reason: "All pending tests approved from dashboard",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "All tests approved",
            message: `${allIds.length} tests approved. Execution starting.`,
          });
          setSelectedTestIds([]);
        },
      }
    );
  };

  // Recent bugs from active or most recent run
  const { data: recentBugs, isLoading: isBugsLoading } = useBugs(
    activeRun?.id
  );

  const handleRunSelect = (runId: string) => {
    setSelectedRunId(runId);
    router.push(`/execution/${runId}`);
  };

  // Agent Chips illumination based on status
  const agentStatus = useMemo(() => {
    const s = activeRun?.status;
    return {
      explorer: s === "exploring",
      planner: s === "planning",
      reviewer: s === "awaiting_review",
      runner: s === "executing",
      verifier: s === "verifying",
    };
  }, [activeRun?.status]);

  return (
    <div className="space-y-8 pb-12">
      {/* 1. HERO SECTION: Start a new test */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-heading text-2xl font-normal text-[#141413]">
              Start a new test
            </h2>
            <p className="text-xs text-[#6B6A64]">
              Configure target URL, feature spec, and testing instructions
            </p>
          </div>
        </div>

        <React.Suspense fallback={null}>
          <StartTestForm />
        </React.Suspense>
      </section>

      {/* 2. KPI ROW (4 Cards) */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Runs */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
          <div className="flex items-center justify-between text-xs text-[#6B6A64] mb-2">
            <span>Total Runs</span>
            <Layers className="w-4 h-4 text-[#8A887F]" />
          </div>
          {isStatsLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-heading text-3xl font-normal text-[#141413]">
              {stats?.total_runs ?? runs?.length ?? 0}
            </div>
          )}
          <p className="text-[11px] text-[#8A887F] mt-1">Autonomous test runs</p>
        </div>

        {/* Confirmed Bugs */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
          <div className="flex items-center justify-between text-xs text-[#6B6A64] mb-2">
            <span>Confirmed Bugs</span>
            <CheckCircle2 className="w-4 h-4 text-[#5E8C61]" />
          </div>
          {isStatsLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-heading text-3xl font-normal text-[#5E8C61]">
              {stats?.confirmed_bugs ?? 0}
            </div>
          )}
          <p className="text-[11px] text-[#5E8C61] mt-1 font-medium">
            3/3 Replays Proven
          </p>
        </div>

        {/* Flaky Bugs */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
          <div className="flex items-center justify-between text-xs text-[#6B6A64] mb-2">
            <span>Flaky Findings</span>
            <AlertTriangle className="w-4 h-4 text-[#D4A02A]" />
          </div>
          {isStatsLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-heading text-3xl font-normal text-[#A67319]">
              {stats?.flaky_bugs ?? 0}
            </div>
          )}
          <p className="text-[11px] text-[#A67319] mt-1 font-medium">
            1-2/3 Replays
          </p>
        </div>

        {/* Pending Reviews */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
          <div className="flex items-center justify-between text-xs text-[#6B6A64] mb-2">
            <span>Pending Reviews</span>
            <Clock className="w-4 h-4 text-[#D97757]" />
          </div>
          {isStatsLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <div className="font-heading text-3xl font-normal text-[#D97757]">
              {stats?.pending_reviews ?? pendingTests.length ?? 0}
            </div>
          )}
          <p className="text-[11px] text-[#8A887F] mt-1">Review gate items</p>
        </div>
      </section>

      {/* 3. TWO COLUMNS: Live Execution (40%) + Recent Runs (60%) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Live Execution (40%) */}
        <div className="lg:col-span-5 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60 mb-4">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-[#D97757]" />
                <h3 className="font-heading text-lg font-normal text-[#141413]">
                  Live execution
                </h3>
              </div>

              {activeRun && (
                <Chip variant={activeRun.status} dot size="xs">
                  {activeRun.status}
                </Chip>
              )}
            </div>

            {!activeRun ? (
              <EmptyState
                icon={PlayCircle}
                title="No active run"
                description="Start a test above to watch autonomous Explorer, Planner, Runner, and Verifier agents execute in real time."
                className="py-10"
              />
            ) : (
              <div className="space-y-4">
                {/* Run Target Info */}
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-semibold text-[#141413]">
                      {extractHostname(activeRun.target_url)}
                    </span>
                    <span className="text-[11px] font-mono text-[#8A887F]">
                      #{activeRun.id.slice(0, 8)}
                    </span>
                  </div>
                  {activeRun.prompt && (
                    <p className="text-xs text-[#6B6A64] mt-1 line-clamp-1">
                      {activeRun.prompt}
                    </p>
                  )}
                </div>

                {/* Stepper */}
                <Stepper status={activeRun.status} />

                {/* Progress bar */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px] font-mono text-[#6B6A64]">
                    <span>Pipeline Progress</span>
                    <span>{activeRun.progress}%</span>
                  </div>
                  <div className="w-full bg-[#F0EEE6] h-2 rounded-full overflow-hidden">
                    <div
                      className="bg-[#D97757] h-full transition-all duration-300 rounded-full"
                      style={{ width: `${activeRun.progress}%` }}
                    />
                  </div>
                </div>

                {/* Active Agent Chips */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-medium text-[#6B6A64] uppercase tracking-wider block">
                    Agent Pipeline
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      { name: "Explorer", active: agentStatus.explorer },
                      { name: "Planner", active: agentStatus.planner },
                      { name: "Reviewer", active: agentStatus.reviewer },
                      { name: "Test Runner", active: agentStatus.runner },
                      { name: "Verifier", active: agentStatus.verifier },
                    ].map((agent) => (
                      <span
                        key={agent.name}
                        className={`text-[11px] px-2.5 py-1 rounded-lg font-mono transition-colors border ${agent.active
                            ? "bg-[#D97757] text-white border-[#D97757] font-semibold shadow-xs animate-pulse"
                            : "bg-[#FAF9F5] text-[#8A887F] border-[#E3DACC]"
                          }`}
                      >
                        {agent.name}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Small Budget Meters */}
                {activeRun.budgets && activeRun.budget_usage && (
                  <div className="grid grid-cols-2 gap-3 pt-2">
                    <BudgetMeter
                      label="Run Time"
                      current={activeRun.budget_usage.elapsed_minutes}
                      max={activeRun.budgets.max_run_minutes}
                      unit="m"
                      size="sm"
                    />
                    <BudgetMeter
                      label="Pages Crawled"
                      current={activeRun.budget_usage.pages_crawled}
                      max={activeRun.budgets.max_pages}
                      size="sm"
                    />
                  </div>
                )}

                {/* Streaming Log Box */}
                <div className="pt-2">
                  <LogViewer logs={logs} onClear={clearLogs} maxHeight="200px" />
                </div>
              </div>
            )}
          </div>

          {activeRun && (
            <div className="pt-4 mt-4 border-t border-[#E3DACC]/60 flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push(`/execution/${activeRun.id}`)}
                className="gap-1.5 text-xs"
              >
                <span>Open full execution view</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          )}
        </div>

        {/* Recent Runs (60%) */}
        <div className="lg:col-span-7 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60 mb-4">
              <h3 className="font-heading text-lg font-normal text-[#141413]">
                Recent runs
              </h3>
              <Link
                href="/execution"
                className="text-xs text-[#D97757] hover:underline font-medium"
              >
                View all runs
              </Link>
            </div>

            {isRunsLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : !runs || runs.length === 0 ? (
              <EmptyState
                icon={Layers}
                title="No test runs found"
                description="Initialize your first testing pipeline above with a target URL."
                className="py-12"
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#E3DACC] text-[#6B6A64]">
                      <th className="pb-2.5 font-semibold">Target & ID</th>
                      <th className="pb-2.5 font-semibold">Prompt</th>
                      <th className="pb-2.5 font-semibold">Status</th>
                      <th className="pb-2.5 font-semibold">Progress</th>
                      <th className="pb-2.5 font-semibold">Started</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E3DACC]/50">
                    {runs.slice(0, 6).map((r) => (
                      <tr
                        key={r.id}
                        onClick={() => handleRunSelect(r.id)}
                        className="hover:bg-[#FAF9F5] transition-colors cursor-pointer group"
                      >
                        <td className="py-3 pr-3">
                          <div className="font-medium text-[#141413] group-hover:text-[#D97757] transition-colors truncate max-w-[150px]">
                            {extractHostname(r.target_url)}
                          </div>
                          <div className="text-[10px] font-mono text-[#8A887F]">
                            #{r.id.slice(0, 8)}
                          </div>
                        </td>

                        <td className="py-3 pr-3 text-[#6B6A64] truncate max-w-[160px]">
                          {r.prompt || "-"}
                        </td>

                        <td className="py-3 pr-3">
                          <Chip variant={r.status} size="xs">
                            {r.status}
                          </Chip>
                        </td>

                        <td className="py-3 pr-3 font-mono">
                          <div className="flex items-center gap-2">
                            <div className="w-16 bg-[#F0EEE6] h-1.5 rounded-full overflow-hidden">
                              <div
                                className="bg-[#D97757] h-full rounded-full"
                                style={{ width: `${r.progress}%` }}
                              />
                            </div>
                            <span className="text-[11px] text-[#8A887F]">
                              {r.progress}%
                            </span>
                          </div>
                        </td>

                        <td className="py-3 text-[#8A887F] font-mono whitespace-nowrap">
                          {formatRelativeTime(r.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* 4. TWO COLUMNS: Needs your review (55%) + Recent bugs (45%) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Needs your review (55%) */}
        <div className="lg:col-span-7 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60 mb-4">
              <div>
                <h3 className="font-heading text-lg font-normal text-[#141413]">
                  Needs your review
                </h3>
                <p className="text-xs text-[#6B6A64]">
                  {awaitingReviewRun
                    ? `Catalog tests awaiting approval for ${extractHostname(awaitingReviewRun.target_url)}`
                    : "Tests awaiting review gate decision"}
                </p>
              </div>

              {awaitingReviewRun && (
                <Link
                  href={`/catalog/${awaitingReviewRun.id}`}
                  className="text-xs text-[#D97757] hover:underline font-medium"
                >
                  Open full catalog
                </Link>
              )}
            </div>

            {isCatalogLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : pendingTests.length === 0 ? (
              <EmptyState
                icon={CheckCircle2}
                title="No tests awaiting review"
                description="All planned tests are either approved, reviewed autonomously, or execution is underway."
                className="py-10"
              />
            ) : (
              <div className="space-y-2">
                {pendingTests.slice(0, 5).map((test) => {
                  const isChecked = selectedTestIds.includes(test.id);
                  return (
                    <div
                      key={test.id}
                      className="p-3 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] flex items-center justify-between gap-3 hover:bg-white transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Checkbox
                          checked={isChecked}
                          onCheckedChange={(checked) => {
                            if (checked) {
                              setSelectedTestIds((prev) => [...prev, test.id]);
                            } else {
                              setSelectedTestIds((prev) =>
                                prev.filter((id) => id !== test.id)
                              );
                            }
                          }}
                        />
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-[#141413] truncate">
                            {test.title}
                          </p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <Chip variant={test.priority} size="xs">
                              {test.priority}
                            </Chip>
                            {test.spec_item_ids.map((id) => (
                              <span
                                key={id}
                                className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#F0EEE6] text-[#6B6A64] border border-[#E3DACC]"
                              >
                                {id}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          router.push(`/catalog/${awaitingReviewRun?.id}`)
                        }
                        className="text-xs text-[#D97757]"
                      >
                        Inspect
                      </Button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {pendingTests.length > 0 && (
            <div className="pt-4 mt-4 border-t border-[#E3DACC]/60 flex items-center justify-between">
              <span className="text-xs text-[#6B6A64]">
                {selectedTestIds.length} of {pendingTests.length} selected
              </span>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={selectedTestIds.length === 0 || isSubmittingReview}
                  onClick={handleApproveSelected}
                  isLoading={isSubmittingReview}
                >
                  Approve selected
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={isSubmittingReview}
                  onClick={handleApproveAll}
                >
                  Approve all & run
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Recent Bugs (45%) */}
        <div className="lg:col-span-5 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60 mb-4">
              <h3 className="font-heading text-lg font-normal text-[#141413]">
                Recent bugs
              </h3>
              {activeRun && (
                <Link
                  href={`/results/${activeRun.id}`}
                  className="text-xs text-[#D97757] hover:underline font-medium"
                >
                  View all
                </Link>
              )}
            </div>

            {isBugsLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : !recentBugs || recentBugs.length === 0 ? (
              <EmptyState
                icon={BugIcon}
                title="No bugs recorded yet"
                description="Playwright workers and the deterministic verifier will log suspected and confirmed bugs here."
                className="py-10"
              />
            ) : (
              <div className="space-y-3">
                {recentBugs.slice(0, 4).map((bug) => (
                  <div
                    key={bug.id}
                    className="p-3 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] space-y-2 hover:bg-white transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        <Chip variant={bug.severity} size="xs">
                          {bug.severity}
                        </Chip>
                        <Chip variant={bug.status} size="xs">
                          {bug.status}
                        </Chip>
                      </div>

                      {/* Replay Pips & Caption */}
                      <ReplayPips
                        replays={bug.replays}
                        status={bug.status}
                        bug={bug}
                        size="sm"
                      />
                    </div>

                    <h4 className="text-xs font-semibold text-[#141413] line-clamp-1">
                      {bug.title}
                    </h4>

                    <div className="flex items-center justify-between pt-1 border-t border-[#E3DACC]/40 text-[11px]">
                      {/* Evidence Icons */}
                      <div className="flex items-center gap-2 text-[#8A887F]">
                        {bug.evidence?.screenshots &&
                          bug.evidence.screenshots.length > 0 && (
                            <span title="Screenshots available">
                              <Camera className="w-3.5 h-3.5" />
                            </span>
                          )}
                        {bug.evidence?.video_url && (
                          <span title="Replay video available">
                            <Video className="w-3.5 h-3.5" />
                          </span>
                        )}
                        {bug.evidence?.trace_url && (
                          <span title="Playwright trace available">
                            <FileSearch className="w-3.5 h-3.5" />
                          </span>
                        )}
                        {bug.repro_script_url && (
                          <span title="Playwright .ts repro script available">
                            <FileCode className="w-3.5 h-3.5 text-[#D97757]" />
                          </span>
                        )}
                      </div>

                      <Link
                        href={`/results/${activeRun?.id}/bugs/${bug.id}`}
                        className="text-[#D97757] hover:underline font-medium inline-flex items-center gap-1"
                      >
                        <span>View bug</span>
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* 5. SPECIAL FEATURE STRIP */}
      <section className="rounded-[16px] p-6 bg-[#F0EEE6] border-l-4 border-l-[#D97757] border border-[#E3DACC] shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-3xl">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#FAF9F5] border border-[#E3DACC] text-[#D97757] text-[11px] font-semibold uppercase tracking-wider">
              <Sparkles className="w-3 h-3 fill-[#D97757]" />
              Special feature
            </div>

            <h3 className="font-heading text-xl font-normal text-[#141413]">
              Verified, not guessed
            </h3>

            <p className="text-xs text-[#6B6A64] leading-relaxed">
              Every suspected bug is replayed 3 times by a deterministic verifier.
              No LLM decides the result. Statuses are honest:{" "}
              <strong className="text-[#141413]">Confirmed (3/3)</strong>,{" "}
              <strong className="text-[#141413]">Flaky (1-2/3)</strong>, or{" "}
              <strong className="text-[#141413]">Not reproduced (0/3)</strong>.
            </p>

            <p className="text-xs text-[#D97757] italic font-medium pt-1">
              &ldquo;It doesn&apos;t just report bugs. It proves them.&rdquo;
            </p>
          </div>

          <div className="shrink-0 flex items-center gap-2">
            <div className="p-3 rounded-xl bg-white border border-[#E3DACC] text-center shadow-xs">
              <div className="font-mono text-sm font-bold text-[#5E8C61]">
                3 of 3
              </div>
              <div className="text-[10px] text-[#8A887F] uppercase tracking-wider">
                Deterministic
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 6. FOOTER */}
      <footer className="pt-6 border-t border-[#E3DACC] text-center text-xs text-[#8A887F]">
        Runs only on authorized staging or local targets • Sandboxed with Docker •
        Human or AI review gate before execution
      </footer>
    </div>
  );
}
