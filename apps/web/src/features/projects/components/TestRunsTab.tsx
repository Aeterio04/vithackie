"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { projectsApi } from "@/features/projects/api";
import { Button } from "@/shared/ui/Button";
import { useToast } from "@/shared/ui/Toast";
import { apiClient } from "@/shared/lib/api/client";
import {
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ArrowRight,
  Shield,
  Layers,
  Bug,
  Code2,
} from "lucide-react";

interface TestRunsTabProps {
  projectId: string;
}

export function TestRunsTab({ projectId }: TestRunsTabProps) {
  const { toast } = useToast();
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [runDetails, setRunDetails] = useState<Record<string, any>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});

  const fetchRuns = useCallback(async () => {
    try {
      const data = await projectsApi.getProjectRuns(projectId);
      setRuns(data || []);
    } catch (err: any) {
      toast({
        type: "error",
        title: "Failed to fetch runs",
        description: err?.message || "Could not load test runs.",
      });
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const toggleExpand = async (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }
    setExpandedRunId(runId);

    if (!runDetails[runId]) {
      setLoadingDetails((prev) => ({ ...prev, [runId]: true }));
      try {
        const detail = await apiClient<any>(`/api/v1/runs/${runId}`);
        setRunDetails((prev) => ({ ...prev, [runId]: detail }));
      } catch (err) {
        // detail fetch fallback
      } finally {
        setLoadingDetails((prev) => ({ ...prev, [runId]: false }));
      }
    }
  };

  const renderStatusBadge = (status?: string, stage?: string) => {
    const s = (status || stage || "unknown").toLowerCase();
    if (s === "completed" || s === "passed") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-status-confirmed-bg text-status-confirmed border border-status-confirmed/30 font-medium">
          <CheckCircle2 className="w-3 h-3" />
          <span>Completed</span>
        </span>
      );
    }
    if (s === "failed") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-status-failed-bg text-status-failed border border-status-failed/30 font-medium">
          <XCircle className="w-3 h-3" />
          <span>Failed</span>
        </span>
      );
    }
    if (s === "running" || s === "executing" || s === "exploring") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-clay-subtle text-clay border border-clay/30 font-medium">
          <Loader2 className="w-3 h-3 animate-spin" />
          <span>{s}</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-cloud text-text-secondary border border-card-border font-medium">
        <Clock className="w-3 h-3" />
        <span>{s}</span>
      </span>
    );
  };

  const formatDuration = (seconds?: number | string) => {
    if (seconds === undefined || seconds === null) return "--";
    const sec = typeof seconds === "string" ? parseFloat(seconds) : seconds;
    if (isNaN(sec) || sec <= 0) return "< 1s";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  if (loading) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
        <p className="text-xs text-text-secondary">Loading test run history...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-card-border rounded-2xl p-6 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-heading text-xl font-normal text-text-primary">
              Test Runs History
            </h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-cloud text-text-secondary border border-card-border">
              {runs.length} {runs.length === 1 ? "run" : "runs"}
            </span>
          </div>
          <p className="text-xs text-text-secondary mt-1">
            Historical autonomous QA sessions, regression executions, and verified defect reports.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchRuns}
            className="gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>

          <Link href="/projects/new">
            <Button variant="primary" size="sm" className="gap-1.5">
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Launch New Run</span>
            </Button>
          </Link>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="bg-white border border-card-border rounded-2xl p-12 text-center max-w-lg mx-auto shadow-xs">
          <div className="w-12 h-12 rounded-2xl bg-cloud border border-card-border flex items-center justify-center mx-auto mb-4 text-clay">
            <Layers className="w-6 h-6" />
          </div>
          <h3 className="font-heading text-lg font-normal text-text-primary mb-1">
            No test runs yet
          </h3>
          <p className="text-xs text-text-secondary leading-relaxed mb-6">
            Execute a saved regression suite or launch an autonomous exploratory session to validate this project.
          </p>
          <Link href="/projects/new">
            <Button variant="primary" size="sm" className="gap-1.5">
              <Play className="w-3.5 h-3.5" />
              <span>Launch Test Run</span>
            </Button>
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((r: any) => {
            const runId = r.runId || r.id;
            const isExpanded = expandedRunId === runId;
            const detail = runDetails[runId];
            const isLoadingDetail = loadingDetails[runId];

            return (
              <div
                key={runId}
                className="bg-white border border-card-border rounded-2xl overflow-hidden shadow-xs hover:border-card-border transition-all"
              >
                <div className="p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-text-primary">
                        {runId}
                      </span>
                      {renderStatusBadge(r.status, r.stage)}
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cloud text-text-secondary border border-card-border">
                        {r.mode || "standard"}
                      </span>
                      {r.golden && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-status-confirmed-bg text-status-confirmed border border-status-confirmed/30 font-medium">
                          Golden Baseline
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary font-mono">
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-text-tertiary" />
                        <span>Duration: {formatDuration(r.duration_seconds || r.duration)}</span>
                      </div>

                      {r.created_at && (
                        <div className="flex items-center gap-1.5">
                          <span>
                            {new Date(r.created_at).toLocaleString(undefined, {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                      )}

                      <div className="flex items-center gap-3">
                        <span className="text-text-primary font-medium">
                          Tests: {r.counts?.tests ?? r.counts?.total_tests ?? 0}
                        </span>
                        {(r.counts?.confirmed ?? r.counts?.confirmed_bugs ?? 0) > 0 && (
                          <span className="text-status-failed font-medium flex items-center gap-1">
                            <Bug className="w-3 h-3" />
                            {r.counts?.confirmed ?? r.counts?.confirmed_bugs} Defects
                          </span>
                        )}
                        {(r.counts?.passed ?? r.counts?.passed_tests ?? 0) > 0 && (
                          <span className="text-status-confirmed font-medium">
                            {r.counts?.passed ?? r.counts?.passed_tests} Passed
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleExpand(runId)}
                      className="gap-1 text-xs text-text-secondary"
                    >
                      <span>{isExpanded ? "Hide Details" : "Show Tests & Errors"}</span>
                      {isExpanded ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </Button>

                    <Link href={`/projects/${projectId}/runs/${runId}/execution`}>
                      <Button variant="secondary" size="sm">
                        Cockpit
                      </Button>
                    </Link>

                    <Link href={`/projects/${projectId}/runs/${runId}/report`}>
                      <Button variant="primary" size="sm" className="gap-1">
                        <span>Report</span>
                        <ArrowRight className="w-3 h-3" />
                      </Button>
                    </Link>
                  </div>
                </div>

                {/* Expanded Details: Tests, Status, and Error Stacks */}
                {isExpanded && (
                  <div className="border-t border-card-border bg-ivory/60 p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-mono font-semibold uppercase text-text-secondary tracking-wider">
                        Per-Test Results & Failure Diagnostics
                      </h4>
                      {isLoadingDetail && (
                        <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                          <Loader2 className="w-3 h-3 animate-spin text-clay" />
                          <span>Loading diagnostics...</span>
                        </div>
                      )}
                    </div>

                    {detail?.test_results && detail.test_results.length > 0 ? (
                      <div className="space-y-3">
                        {detail.test_results.map((tr: any, idx: number) => {
                          const isFail = tr.status === "failed" || tr.status === "assertion_failure";
                          return (
                            <div
                              key={tr.id || idx}
                              className={`rounded-xl p-3.5 border ${
                                isFail
                                  ? "bg-status-failed-bg/30 border-status-failed/30"
                                  : "bg-white border-card-border"
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2 mb-2">
                                <div className="flex items-center gap-2">
                                  {isFail ? (
                                    <XCircle className="w-4 h-4 text-status-failed shrink-0" />
                                  ) : (
                                    <CheckCircle2 className="w-4 h-4 text-status-confirmed shrink-0" />
                                  )}
                                  <span className="text-xs font-semibold text-text-primary">
                                    {tr.title || tr.name || `Test Case #${idx + 1}`}
                                  </span>
                                </div>

                                <div className="flex items-center gap-2 text-xs font-mono text-text-tertiary">
                                  <span>{formatDuration(tr.duration_ms ? tr.duration_ms / 1000 : tr.duration)}</span>
                                  <span
                                    className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                                      isFail
                                        ? "bg-status-failed text-white"
                                        : "bg-status-confirmed text-white"
                                    }`}
                                  >
                                    {tr.status}
                                  </span>
                                </div>
                              </div>

                              {/* Error message and Stack */}
                              {(tr.error_message || tr.error || tr.stack_trace) && (
                                <div className="mt-3 bg-text-primary text-[#E3DACC] p-3 rounded-lg text-xs font-mono space-y-1.5 overflow-x-auto">
                                  {tr.error_message && (
                                    <div className="text-rose-400 font-semibold">
                                      Error: {tr.error_message}
                                    </div>
                                  )}
                                  {tr.stack_trace && (
                                    <pre className="text-[11px] text-[#A8A69F] whitespace-pre-wrap leading-relaxed">
                                      {tr.stack_trace}
                                    </pre>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="p-4 bg-white border border-card-border rounded-xl text-center text-xs text-text-secondary">
                        {isLoadingDetail
                          ? "Fetching test results..."
                          : "No individual test failure traces recorded for this run."}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
