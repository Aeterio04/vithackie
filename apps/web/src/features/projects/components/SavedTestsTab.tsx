"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { projectsApi, SavedTestItem } from "@/features/projects/api";
import { Button } from "@/shared/ui/Button";
import { useToast } from "@/shared/ui/Toast";
import {
  Bookmark,
  Play,
  PlayCircle,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  FileCode2,
  Layers,
  RefreshCw,
  Cpu,
  ArrowRight,
  ExternalLink,
} from "lucide-react";

interface SavedTestsTabProps {
  projectId: string;
}

export function SavedTestsTab({ projectId }: SavedTestsTabProps) {
  const { toast } = useToast();
  const [tests, setTests] = useState<SavedTestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningAll, setRunningAll] = useState(false);
  const [runningTestId, setRunningTestId] = useState<string | null>(null);
  
  // Active run tracking for polling
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRunStatus, setActiveRunStatus] = useState<string | null>(null);
  const [activeRunSummary, setActiveRunSummary] = useState<any | null>(null);

  const fetchTests = useCallback(async () => {
    try {
      const data = await projectsApi.getSavedTests(projectId);
      setTests(data);
    } catch (err: any) {
      toast({
        type: "error",
        title: "Failed to load saved tests",
        description: err?.message || "Could not retrieve saved tests from server.",
      });
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    fetchTests();
  }, [fetchTests]);

  // Poll active run if running
  useEffect(() => {
    if (!activeRunId) return;

    const interval = setInterval(async () => {
      try {
        const runs = await projectsApi.getProjectRuns(projectId);
        const match = runs.find((r: any) => r.runId === activeRunId || r.id === activeRunId);
        if (match) {
          const status = match.status || match.stage;
          setActiveRunStatus(status);
          setActiveRunSummary(match);

          if (status === "completed" || status === "failed" || status === "aborted") {
            setActiveRunId(null);
            fetchTests(); // refresh test outcomes
            toast({
              type: status === "completed" ? "success" : "warning",
              title: `Run ${status}`,
              description: `Run ${match.runId || activeRunId} finished with status: ${status}`,
            });
          }
        }
      } catch {
        // ignore polling transient errors
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [activeRunId, projectId, fetchTests, toast]);

  const handleRunAll = async () => {
    setRunningAll(true);
    try {
      const res = await projectsApi.runAllSavedTests(projectId);
      setActiveRunId(res.runId);
      setActiveRunStatus("running");
      toast({
        type: "info",
        title: "Test Suite Dispatched",
        description: `Executing ${res.totalTests} tests deterministically across 2 workers without AI.`,
      });
    } catch (err: any) {
      toast({
        type: "error",
        title: "Failed to run tests",
        description: err?.message || "Could not trigger suite run.",
      });
    } finally {
      setRunningAll(false);
    }
  };

  const handleRunSingle = async (testId: string, testName: string) => {
    setRunningTestId(testId);
    try {
      const res = await projectsApi.runSavedTest(projectId, testId);
      setActiveRunId(res.runId);
      setActiveRunStatus("running");
      toast({
        type: "info",
        title: "Test Dispatched",
        description: `Running "${testName}" with deterministic runner.`,
      });
    } catch (err: any) {
      toast({
        type: "error",
        title: "Execution Error",
        description: err?.message || "Could not run test.",
      });
    } finally {
      setRunningTestId(null);
    }
  };

  const renderResultBadge = (result?: string | null) => {
    if (!result || result === "not_run" || result === "unknown") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-cloud text-text-tertiary border border-card-border">
          <Clock className="w-3 h-3" />
          <span>Not run</span>
        </span>
      );
    }
    if (result === "passed" || result === "pass") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-status-confirmed-bg text-status-confirmed border border-status-confirmed/30 font-medium">
          <CheckCircle2 className="w-3 h-3" />
          <span>Passed</span>
        </span>
      );
    }
    if (result === "assertion_failure" || result === "failed") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-status-failed-bg text-status-failed border border-status-failed/30 font-medium">
          <XCircle className="w-3 h-3" />
          <span>Failed</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-status-flaky-bg text-status-flaky border border-status-flaky/30 font-medium">
        <AlertTriangle className="w-3 h-3" />
        <span>{result}</span>
      </span>
    );
  };

  if (loading) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
        <p className="text-xs text-text-secondary">Loading saved test catalog...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-card-border rounded-2xl p-6 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-heading text-xl font-normal text-text-primary">
              Saved Test Catalog
            </h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-cloud text-text-secondary border border-card-border">
              {tests.length} {tests.length === 1 ? "test" : "tests"}
            </span>
          </div>
          <p className="text-xs text-text-secondary mt-1 max-w-xl">
            Deterministic Playwright test suite for regression testing. Runs execute stored test scripts directly across 2 workers without calling AI models.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchTests}
            className="gap-1.5"
            disabled={loading}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleRunAll}
            disabled={runningAll || tests.length === 0 || !!activeRunId}
            className="gap-2 shadow-xs"
          >
            {runningAll ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current" />
            )}
            <span>Run All ({tests.length})</span>
          </Button>
        </div>
      </div>

      {/* Active Run Banner */}
      {activeRunId && (
        <div className="bg-clay-subtle border border-clay/30 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-white border border-clay/30 flex items-center justify-center text-clay">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-text-primary">
                  Run {activeRunId}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-clay text-white uppercase tracking-wider font-semibold">
                  {activeRunStatus || "running"}
                </span>
              </div>
              <p className="text-[11px] text-text-secondary mt-0.5">
                Deterministic worker pool active (2 workers). Executing saved scripts...
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link href={`/projects/${projectId}/runs/${activeRunId}/execution`}>
              <Button variant="secondary" size="sm" className="gap-1 text-xs">
                <span>View Execution</span>
                <ArrowRight className="w-3 h-3" />
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Tests Catalog List */}
      {tests.length === 0 ? (
        <div className="bg-white border border-card-border rounded-2xl p-12 text-center max-w-lg mx-auto shadow-xs">
          <div className="w-12 h-12 rounded-2xl bg-cloud border border-card-border flex items-center justify-center mx-auto mb-4 text-clay">
            <Bookmark className="w-6 h-6" />
          </div>
          <h3 className="font-heading text-lg font-normal text-text-primary mb-1">
            No saved tests yet
          </h3>
          <p className="text-xs text-text-secondary leading-relaxed mb-6">
            When you run exploration runs and discover verified bug reproductions or passing user journeys, you can save them into your project&apos;s regression catalog here.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link href={`/projects/new`}>
              <Button variant="primary" size="sm" className="gap-1.5">
                <Play className="w-3.5 h-3.5" />
                <span>Launch Exploration Run</span>
              </Button>
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {tests.map((test) => {
            const isThisRunning = runningTestId === test.id;
            const result = test.last_result || test.lastResult;
            return (
              <div
                key={test.id}
                className="bg-white border border-card-border rounded-2xl p-4 sm:p-5 shadow-xs hover:border-card-border transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="space-y-2 max-w-2xl">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-heading font-medium text-text-primary text-base">
                      {test.name}
                    </span>
                    {renderResultBadge(result)}
                  </div>

                  {test.description && (
                    <p className="text-xs text-text-secondary line-clamp-2">
                      {test.description}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-tertiary font-mono">
                    <div className="flex items-center gap-1.5">
                      <FileCode2 className="w-3.5 h-3.5" />
                      <span className="truncate max-w-[280px]" title={test.script_path}>
                        {test.script_path || "playwright/test.spec.ts"}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{new Date(test.created_at).toLocaleDateString()}</span>
                    </div>

                    {test.origin_run_id && (
                      <div className="flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5" />
                        <span>Run: {test.origin_run_id.slice(0, 10)}</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleRunSingle(test.id, test.name)}
                    disabled={isThisRunning || !!activeRunId}
                    className="gap-1.5"
                  >
                    {isThisRunning ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <PlayCircle className="w-3.5 h-3.5 text-clay" />
                    )}
                    <span>Run</span>
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
