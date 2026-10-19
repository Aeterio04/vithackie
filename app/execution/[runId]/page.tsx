"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  useRun,
  useExecution,
  useTests,
  useBugs,
  useCancelRun,
  useRetryRun,
} from "@/lib/api/hooks";
import { useRunStream } from "@/hooks/useRunStream";
import { useUiStore } from "@/lib/store/uiStore";
import { useToast } from "@/components/ui/Toast";
import { Stepper } from "@/components/ui/Stepper";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { ConnectionBadge } from "@/components/ui/ConnectionBadge";
import { WorkerCard } from "@/components/ui/WorkerCard";
import { BudgetMeter } from "@/components/ui/BudgetMeter";
import { LogViewer } from "@/components/ui/LogViewer";
import { ReplayPips } from "@/components/ui/ReplayPips";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/Dialog";
import { extractHostname, formatDuration, formatRelativeTime } from "@/lib/utils";
import {
  PlayCircle,
  AlertOctagon,
  RotateCcw,
  Clock,
  Layers,
  ArrowRight,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Sliders,
  Terminal,
} from "lucide-react";

export default function ExecutionRunPage() {
  const params = useParams();
  const runId = params.runId as string;
  const router = useRouter();
  const { toast } = useToast();
  const { setSelectedRunId } = useUiStore();

  useEffect(() => {
    if (runId) setSelectedRunId(runId);
  }, [runId, setSelectedRunId]);

  const { data: run, isLoading: isRunLoading } = useRun(runId);
  const isFinished =
    run?.status === "completed" ||
    run?.status === "failed" ||
    run?.status === "cancelled" ||
    run?.status === "budget_exhausted";

  // SSE Stream with auto-stop when finished
  const { connectionState, logs, clearLogs } = useRunStream(runId, isFinished);

  const { data: execution, isLoading: isExecutionLoading } = useExecution(runId);
  const { data: tests, isLoading: isTestsLoading } = useTests(runId);
  const { data: bugs } = useBugs(runId);

  // Actions
  const { mutate: cancelRun, isPending: isCancelling } = useCancelRun();
  const { mutate: retryRun, isPending: isRetrying } = useRetryRun();

  const [isCancelDialogOpen, setIsCancelDialogOpen] = useState(false);

  const handleConfirmCancel = () => {
    cancelRun(runId, {
      onSuccess: () => {
        toast({
          type: "info",
          title: "Run cancelled",
          message: "All worker containers are terminating.",
        });
        setIsCancelDialogOpen(false);
      },
      onError: (err) => {
        toast({
          type: "error",
          title: "Failed to cancel run",
          message: err.message,
        });
      },
    });
  };

  const handleRetryErrored = () => {
    retryRun(runId, {
      onSuccess: () => {
        toast({
          type: "success",
          title: "Retry dispatched",
          message: "Re-queueing errored infrastructure tests.",
        });
      },
      onError: (err) => {
        toast({
          type: "error",
          title: "Retry failed",
          message: err.message,
        });
      },
    });
  };

  // Check if any tests have infrastructure error
  const erroredTestsCount = useMemo(() => {
    return (tests || []).filter((t) => t.status === "error").length;
  }, [tests]);

  // Verification items: suspected or currently verifying bugs
  const verifyingBugs = useMemo(() => {
    return (bugs || []).filter(
      (b) => b.status === "verifying" || b.status === "suspected" || b.replays.length > 0
    );
  }, [bugs]);

  const workers = execution?.workers || [];
  const allTests = tests || execution?.tests || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* 1. Header Card */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="font-heading text-2xl font-normal text-[#141413]">
              {run ? extractHostname(run.target_url) : "Loading target..."}
            </h1>
            <Chip variant={run?.status || "neutral"} size="sm">
              {run?.status || "loading"}
            </Chip>
            <ConnectionBadge state={connectionState} />
          </div>

          <div className="flex items-center gap-3 text-xs font-mono text-[#8A887F]">
            <span>Run ID: {runId}</span>
            <span>•</span>
            <span>Started: {formatRelativeTime(run?.created_at)}</span>
            {run?.finished_at && (
              <>
                <span>•</span>
                <span>Finished: {formatRelativeTime(run.finished_at)}</span>
              </>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {erroredTestsCount > 0 && !isFinished && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRetryErrored}
              isLoading={isRetrying}
              className="gap-1.5 text-xs text-[#C4473A] border-[#F2CAC5] hover:bg-[#FAEBE9]"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry Errored Tests ({erroredTestsCount})</span>
            </Button>
          )}

          {!isFinished && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setIsCancelDialogOpen(true)}
              disabled={isCancelling}
              className="gap-1.5"
            >
              <AlertOctagon className="w-3.5 h-3.5" />
              <span>Cancel Run</span>
            </Button>
          )}

          <Button
            variant="secondary"
            size="sm"
            onClick={() => router.push(`/results/${runId}`)}
            className="gap-1.5"
          >
            <span>Results & Bugs</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* 2. 6-Step Stepper */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs">
        <Stepper status={run?.status || "executing"} />
      </div>

      {/* 3. Awaiting Review Banner */}
      {run?.status === "awaiting_review" && (
        <div className="bg-[#FAF9F5] border-2 border-[#D97757] rounded-[16px] p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4 animate-in fade-in">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#D97757]" />
              <h3 className="font-heading text-lg font-normal text-[#141413]">
                Human Review Gate: Approval Required
              </h3>
            </div>
            <p className="text-xs text-[#6B6A64]">
              The Planner agent has built the test catalog. Execution is paused
              until you review, edit, or approve tests.
            </p>
          </div>

          <Button
            variant="primary"
            size="md"
            onClick={() => router.push(`/catalog/${runId}`)}
            className="gap-1.5 shrink-0"
          >
            <span>Open Test Catalog</span>
            <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* 4. Budget Meters Row */}
      {run?.budgets && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white border border-[#E3DACC] rounded-[16px] p-4 shadow-xs">
            <BudgetMeter
              label="Run Minutes"
              current={execution?.budget_usage?.elapsed_minutes ?? run.budget_usage?.elapsed_minutes ?? 0}
              max={run.budgets.max_run_minutes}
              unit="m"
            />
          </div>

          <div className="bg-white border border-[#E3DACC] rounded-[16px] p-4 shadow-xs">
            <BudgetMeter
              label="Pages Crawled"
              current={execution?.budget_usage?.pages_crawled ?? run.budget_usage?.pages_crawled ?? 0}
              max={run.budgets.max_pages}
            />
          </div>

          <div className="bg-white border border-[#E3DACC] rounded-[16px] p-4 shadow-xs">
            <BudgetMeter
              label="Steps Executed"
              current={execution?.budget_usage?.steps_executed ?? run.budget_usage?.steps_executed ?? 0}
              max={run.budgets.max_steps_per_test * 10}
            />
          </div>

          <div className="bg-white border border-[#E3DACC] rounded-[16px] p-4 shadow-xs">
            <BudgetMeter
              label="Parallel Workers"
              current={execution?.budget_usage?.active_workers ?? run.budget_usage?.active_workers ?? workers.length}
              max={run.budgets.parallel_workers}
            />
          </div>
        </div>
      )}

      {/* 5. DETERMINISTIC VERIFICATION PANEL */}
      {verifyingBugs.length > 0 && (
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60">
            <div>
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-[#D97757]" />
                <h3 className="font-heading text-lg font-normal text-[#141413]">
                  Deterministic Verification Trials (3x Replay)
                </h3>
              </div>
              <p className="text-xs text-[#6B6A64]">
                Suspected bugs are replayed 3 times in clean Docker sandboxes.
                No LLM decides the result.
              </p>
            </div>

            <span className="text-xs font-mono text-[#D97757] font-semibold bg-[#F6EDE8] px-2.5 py-1 rounded-full border border-[#F0D5C9]">
              {verifyingBugs.length} Suspected Bug(s)
            </span>
          </div>

          <div className="space-y-3">
            {verifyingBugs.map((b) => (
              <div
                key={b.id}
                className="p-3.5 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-white transition-colors"
              >
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Chip variant={b.severity} size="xs">
                      {b.severity}
                    </Chip>
                    <Chip variant={b.status} size="xs">
                      {b.status}
                    </Chip>
                    <span className="text-xs font-mono text-[#8A887F]">
                      Source: {b.source === "test_runner" ? "Test Runner" : "Exploratory"}
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-[#141413] truncate">
                    {b.title}
                  </h4>
                </div>

                {/* Replay Pips & Live Progress */}
                <div className="flex items-center gap-4 shrink-0">
                  <div className="flex flex-col items-end">
                    <ReplayPips
                      replays={b.replays}
                      status={b.status}
                      bug={b}
                      size="md"
                    />
                    <span className="text-[10px] text-[#8A887F] font-mono mt-0.5">
                      3 deterministic passes
                    </span>
                  </div>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => router.push(`/results/${runId}/bugs/${b.id}`)}
                    className="text-xs text-[#D97757]"
                  >
                    Details
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. Parallel Workers Grid (up to 4 + Exploratory Lane) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-heading text-lg font-normal text-[#141413]">
              Sandboxed Playwright Workers
            </h3>
            <p className="text-xs text-[#6B6A64]">
              Isolated Chromium instances running scheduled and exploratory
              interaction scripts
            </p>
          </div>
          <span className="text-xs font-mono text-[#8A887F]">
            {workers.length} active worker(s)
          </span>
        </div>

        {isExecutionLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-64 w-full" />
            ))}
          </div>
        ) : workers.length === 0 ? (
          <EmptyState
            icon={PlayCircle}
            title="Waiting for worker assignment..."
            description="Docker containers are provisioning for the active test plan."
            className="py-10"
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {workers.map((worker) => (
              <WorkerCard key={worker.id} worker={worker} />
            ))}
          </div>
        )}
      </div>

      {/* 7. TWO COLUMNS: Test Execution List (60%) + Streaming Logs (40%) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Test Execution List */}
        <div className="lg:col-span-7 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60">
            <h3 className="font-heading text-lg font-normal text-[#141413]">
              Test Execution Queue ({allTests.length})
            </h3>
            <span className="text-[11px] text-[#8A887F] font-mono">
              Infrastructure errors excluded from bugs
            </span>
          </div>

          {isTestsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : allTests.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="No tests queued yet"
              description="Tests will appear once Planner and Review gate finalize the catalog."
              className="py-8"
            />
          ) : (
            <div className="divide-y divide-[#E3DACC]/50 max-h-[460px] overflow-y-auto">
              {allTests.map((t) => (
                <div
                  key={t.id}
                  className="py-3 flex items-center justify-between gap-3 text-xs hover:bg-[#FAF9F5] px-2 rounded-lg transition-colors"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-[#141413] truncate">
                      {t.title}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 text-[11px] text-[#8A887F] font-mono">
                      {t.worker_id && <span>Worker: {t.worker_id}</span>}
                      {t.duration_ms && (
                        <span>Duration: {formatDuration(t.duration_ms)}</span>
                      )}
                    </div>
                    {t.error_message && (
                      <p className="text-[11px] text-[#C4473A] mt-1 font-mono">
                        Error: {t.error_message}
                      </p>
                    )}
                  </div>

                  <Chip variant={t.status} size="xs" dot>
                    {t.status}
                  </Chip>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Streaming Logs Box */}
        <div className="lg:col-span-5 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-[#D97757]" />
              <h3 className="font-heading text-lg font-normal text-[#141413]">
                Live Agent & Worker Logs
              </h3>
            </div>
          </div>

          <LogViewer logs={logs} onClear={clearLogs} maxHeight="400px" />
        </div>
      </div>

      {/* CANCEL RUN DIALOG */}
      <Dialog open={isCancelDialogOpen} onOpenChange={setIsCancelDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel Running Pipeline?</DialogTitle>
            <DialogDescription>
              This will stop all parallel Playwright workers, terminate Docker
              containers, and finalize the run with status &quot;cancelled&quot;.
              Completed test evidence will still be preserved.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsCancelDialogOpen(false)}
            >
              Keep Running
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={handleConfirmCancel}
              isLoading={isCancelling}
            >
              Yes, Cancel Run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
