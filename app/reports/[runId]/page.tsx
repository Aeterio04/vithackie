"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useReport } from "@/lib/api/hooks";
import { useUiStore } from "@/lib/store/uiStore";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { ReplayPips } from "@/components/ui/ReplayPips";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/DropdownMenu";
import { API_ENDPOINTS } from "@/lib/api/config";
import { extractHostname, formatDuration, formatRelativeTime } from "@/lib/utils";
import {
  FileBarChart2,
  Download,
  FileCode,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Bot,
  User,
  Info,
} from "lucide-react";

export default function ReportDetailPage() {
  const params = useParams();
  const runId = params.runId as string;
  const router = useRouter();
  const { setSelectedRunId } = useUiStore();

  useEffect(() => {
    if (runId) setSelectedRunId(runId);
  }, [runId, setSelectedRunId]);

  const { data: report, isLoading } = useReport(runId);
  const [isNotReproOpen, setIsNotReproOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-6xl mx-auto pb-16">
        <Skeleton className="h-32 w-full" />
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!report) {
    return (
      <EmptyState
        title="Report not generated yet"
        description="This run does not have a finalized report available."
        action={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => router.push(`/execution/${runId}`)}
          >
            Check Execution Status
          </Button>
        }
      />
    );
  }

  const run = report.run;
  const funnel = report.verification_funnel;
  const totalFunnel =
    (funnel.confirmed || 0) + (funnel.flaky || 0) + (funnel.not_reproduced || 0);

  const confirmedPct =
    totalFunnel > 0 ? Math.round((funnel.confirmed / totalFunnel) * 100) : 0;
  const flakyPct =
    totalFunnel > 0 ? Math.round((funnel.flaky / totalFunnel) * 100) : 0;
  const notReproPct =
    totalFunnel > 0 ? 100 - confirmedPct - flakyPct : 0;

  // Group bugs
  const confirmedBugs = report.bugs.filter((b) => b.status === "confirmed");
  const flakyBugs = report.bugs.filter((b) => b.status === "flaky");
  const notReproBugs = report.bugs.filter((b) => b.status === "not_reproduced");

  const specCov = report.spec_coverage;
  const coveragePct =
    specCov.total_items > 0
      ? Math.round((specCov.covered_items / specCov.total_items) * 100)
      : 100;

  const handleExport = (format: "html" | "pdf" | "json" | "csv") => {
    const exportUrl = API_ENDPOINTS.RUN_REPORT_EXPORT(runId, format);
    window.open(exportUrl, "_blank");
  };

  const handleDownloadTests = () => {
    const testsUrl = API_ENDPOINTS.RUN_TESTS_EXPORT(runId);
    window.open(testsUrl, "_blank");
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-20">
      {/* 1. SUMMARY HEADER */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-normal text-[#141413]">
              {extractHostname(run.target_url)}
            </h1>
            <Chip variant={run.status} size="sm">
              {run.status}
            </Chip>
            <span className="text-xs font-mono text-[#8A887F]">
              Mode: {run.review_mode}
            </span>
          </div>

          <p className="text-xs text-[#6B6A64]">
            QA Verification Report for Run{" "}
            <span className="font-mono text-[#141413]">#{run.id}</span>
          </p>

          <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-[#8A887F] pt-1">
            <span>Started: {formatRelativeTime(run.created_at)}</span>
            <span>•</span>
            <span>
              Duration:{" "}
              {run.budget_usage
                ? `${run.budget_usage.elapsed_minutes} min`
                : "-"}
            </span>
            <span>•</span>
            <span>
              Pages Crawled: {report.budget_usage.pages_crawled} /{" "}
              {run.budgets?.max_pages ?? "-"}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5 shrink-0">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5">
                <Download className="w-3.5 h-3.5" />
                <span>Export Report</span>
                <ChevronDown className="w-3 h-3 text-[#8A887F]" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={() => handleExport("html")}>
                HTML Executive Summary
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("pdf")}>
                PDF Report Archive
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("json")}>
                Machine-Readable JSON
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("csv")}>
                CSV Test Breakdown
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            variant="primary"
            size="sm"
            onClick={handleDownloadTests}
            className="gap-1.5"
          >
            <FileCode className="w-4 h-4" />
            <span>Download Reusable Tests (.zip)</span>
          </Button>
        </div>
      </div>

      {/* 2. METRICS CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Workflow Completion */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs">
          <span className="text-xs font-semibold text-[#6B6A64] block mb-1">
            Workflow Completion
          </span>
          <div className="font-heading text-3xl font-normal text-[#141413]">
            {report.metrics.workflow_completion_pct !== null &&
            report.metrics.workflow_completion_pct !== undefined
              ? `${report.metrics.workflow_completion_pct}%`
              : "-"}
          </div>
          <p className="text-[11px] text-[#8A887F] mt-1">
            Planned interaction flows executed to completion
          </p>
        </div>

        {/* Finding Verification */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs">
          <span className="text-xs font-semibold text-[#6B6A64] block mb-1">
            Finding Verification
          </span>
          <div className="font-heading text-3xl font-normal text-[#5E8C61]">
            {report.metrics.finding_verification_pct !== null &&
            report.metrics.finding_verification_pct !== undefined
              ? `${report.metrics.finding_verification_pct}%`
              : "-"}
          </div>
          <p className="text-[11px] text-[#5E8C61] mt-1 font-medium">
            Suspected issues replayed 3x deterministically
          </p>
        </div>

        {/* Evidence Completeness */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs">
          <span className="text-xs font-semibold text-[#6B6A64] block mb-1">
            Evidence Completeness
          </span>
          <div className="font-heading text-3xl font-normal text-[#141413]">
            {report.metrics.evidence_completeness_pct !== null &&
            report.metrics.evidence_completeness_pct !== undefined
              ? `${report.metrics.evidence_completeness_pct}%`
              : "-"}
          </div>
          <p className="text-[11px] text-[#8A887F] mt-1">
            Findings with video, trace, logs, and repro scripts
          </p>
        </div>
      </div>

      {/* 3. VERIFICATION FUNNEL (Stacked Bar built with divs) */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60">
          <div>
            <h3 className="font-heading text-lg font-normal text-[#141413]">
              Deterministic Verification Funnel
            </h3>
            <p className="text-xs text-[#6B6A64]">
              How suspected issues resolved after 3 deterministic replays in
              Docker sandboxes
            </p>
          </div>

          <span className="text-xs font-mono text-[#141413] font-semibold">
            Total Suspected: {totalFunnel}
          </span>
        </div>

        {totalFunnel === 0 ? (
          <p className="text-xs text-[#8A887F] italic py-4 text-center">
            No bugs or replays recorded for this run.
          </p>
        ) : (
          <div className="space-y-3">
            {/* Pure Div Stacked Bar */}
            <div className="w-full h-8 bg-[#F0EEE6] rounded-xl overflow-hidden flex shadow-inner">
              {funnel.confirmed > 0 && (
                <div
                  style={{ width: `${confirmedPct}%` }}
                  className="bg-[#5E8C61] h-full flex items-center justify-center text-white text-xs font-semibold font-mono transition-all duration-500"
                  title={`Confirmed (3/3): ${funnel.confirmed} (${confirmedPct}%)`}
                >
                  {confirmedPct > 8 ? `${funnel.confirmed} (${confirmedPct}%)` : ""}
                </div>
              )}

              {funnel.flaky > 0 && (
                <div
                  style={{ width: `${flakyPct}%` }}
                  className="bg-[#D4A02A] h-full flex items-center justify-center text-white text-xs font-semibold font-mono transition-all duration-500"
                  title={`Flaky (1-2/3): ${funnel.flaky} (${flakyPct}%)`}
                >
                  {flakyPct > 8 ? `${funnel.flaky} (${flakyPct}%)` : ""}
                </div>
              )}

              {funnel.not_reproduced > 0 && (
                <div
                  style={{ width: `${notReproPct}%` }}
                  className="bg-[#C4473A] h-full flex items-center justify-center text-white text-xs font-semibold font-mono transition-all duration-500"
                  title={`Not Reproduced (0/3): ${funnel.not_reproduced} (${notReproPct}%)`}
                >
                  {notReproPct > 8 ? `${funnel.not_reproduced} (${notReproPct}%)` : ""}
                </div>
              )}
            </div>

            {/* Funnel Legend */}
            <div className="flex flex-wrap items-center justify-between gap-4 pt-1 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-[#5E8C61]" />
                <span className="font-medium text-[#141413]">
                  Confirmed: {funnel.confirmed} ({confirmedPct}%)
                </span>
                <span className="text-[#8A887F] text-[11px]">
                  (3 of 3 replays reproduced)
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-[#D4A02A]" />
                <span className="font-medium text-[#141413]">
                  Flaky: {funnel.flaky} ({flakyPct}%)
                </span>
                <span className="text-[#8A887F] text-[11px]">
                  (1-2 of 3 replays)
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-[#C4473A]" />
                <span className="font-medium text-[#141413]">
                  Not Reproduced: {funnel.not_reproduced} ({notReproPct}%)
                </span>
                <span className="text-[#8A887F] text-[11px]">
                  (0 of 3 replays)
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 4. SPEC COVERAGE */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]/60">
          <div>
            <h3 className="font-heading text-lg font-normal text-[#141413]">
              Specification Coverage
            </h3>
            <p className="text-xs text-[#6B6A64]">
              Validation of feature acceptance criteria and spec items
            </p>
          </div>

          <span className="text-xs font-mono font-semibold text-[#141413]">
            {specCov.covered_items} / {specCov.total_items} Items ({coveragePct}%)
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-[#F0EEE6] h-2.5 rounded-full overflow-hidden">
          <div
            className="bg-[#D97757] h-full rounded-full transition-all duration-300"
            style={{ width: `${coveragePct}%` }}
          />
        </div>

        {/* Covered items */}
        {specCov.covered_item_ids.length > 0 && (
          <div className="space-y-1.5 pt-2">
            <span className="text-xs font-semibold text-[#5E8C61] block">
              Covered Specification Items ({specCov.covered_item_ids.length})
            </span>
            <div className="flex flex-wrap gap-1.5">
              {specCov.covered_item_ids.map((id) => (
                <span
                  key={id}
                  className="px-2 py-0.5 rounded-lg text-xs font-mono bg-[#EBF2EB] border border-[#D2E3D3] text-[#47704A]"
                >
                  ✓ {id}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Uncovered items */}
        {specCov.uncovered_items.length > 0 && (
          <div className="space-y-2 pt-3 border-t border-[#E3DACC]/60">
            <span className="text-xs font-semibold text-[#C4473A] block">
              Uncovered Specification Items ({specCov.uncovered_items.length})
            </span>
            <div className="space-y-1.5">
              {specCov.uncovered_items.map((item) => (
                <div
                  key={item.id}
                  className="p-2.5 rounded-lg bg-[#FAF9F5] border border-[#E3DACC] text-xs flex items-center justify-between"
                >
                  <span className="font-mono font-semibold text-[#C4473A]">
                    {item.id}
                  </span>
                  <span className="text-[#6B6A64]">{item.title}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 5. BUGS GROUPED BY STATUS (Not Reproduced Collapsed) */}
      <div className="space-y-4">
        <h3 className="font-heading text-xl font-normal text-[#141413]">
          Detailed Findings Breakdown
        </h3>

        {/* Group A: Confirmed Bugs (3/3) */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-[#5E8C61]" />
              <h4 className="font-semibold text-sm text-[#141413]">
                Confirmed Bugs ({confirmedBugs.length})
              </h4>
            </div>
            <span className="text-xs font-mono text-[#5E8C61]">
              Reproduced in 3/3 Replays
            </span>
          </div>

          {confirmedBugs.length === 0 ? (
            <p className="text-xs text-[#8A887F] italic py-2">
              No confirmed bugs detected.
            </p>
          ) : (
            <div className="space-y-2">
              {confirmedBugs.map((b) => (
                <div
                  key={b.id}
                  className="p-3 rounded-xl border border-[#D2E3D3] bg-[#EBF2EB]/30 flex items-center justify-between gap-3"
                >
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2">
                      <Chip variant={b.severity} size="xs">
                        {b.severity}
                      </Chip>
                      <h5 className="font-semibold text-xs text-[#141413] truncate">
                        {b.title}
                      </h5>
                    </div>
                    <p className="text-xs text-[#6B6A64] line-clamp-1">
                      {b.actual}
                    </p>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <ReplayPips
                      replays={b.replays}
                      status={b.status}
                      bug={b}
                      size="sm"
                    />
                    <Link
                      href={`/results/${runId}/bugs/${b.id}`}
                      className="text-xs text-[#D97757] hover:underline font-medium inline-flex items-center gap-1"
                    >
                      <span>Evidence</span>
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Group B: Flaky Findings (1-2/3) */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-[#D4A02A]" />
              <h4 className="font-semibold text-sm text-[#141413]">
                Flaky Findings ({flakyBugs.length})
              </h4>
            </div>
            <span className="text-xs font-mono text-[#A67319]">
              Reproduced in 1-2/3 Replays
            </span>
          </div>

          {flakyBugs.length === 0 ? (
            <p className="text-xs text-[#8A887F] italic py-2">
              No flaky findings detected.
            </p>
          ) : (
            <div className="space-y-2">
              {flakyBugs.map((b) => (
                <div
                  key={b.id}
                  className="p-3 rounded-xl border border-[#F4E2BD] bg-[#FBF4E6]/30 flex items-center justify-between gap-3"
                >
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2">
                      <Chip variant={b.severity} size="xs">
                        {b.severity}
                      </Chip>
                      <h5 className="font-semibold text-xs text-[#141413] truncate">
                        {b.title}
                      </h5>
                    </div>
                    <p className="text-xs text-[#6B6A64] line-clamp-1">
                      {b.actual}
                    </p>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <ReplayPips
                      replays={b.replays}
                      status={b.status}
                      bug={b}
                      size="sm"
                    />
                    <Link
                      href={`/results/${runId}/bugs/${b.id}`}
                      className="text-xs text-[#D97757] hover:underline font-medium inline-flex items-center gap-1"
                    >
                      <span>Evidence</span>
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Group C: Not Reproduced (0/3) - Collapsible, Collapsed by default */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] overflow-hidden shadow-xs">
          <button
            onClick={() => setIsNotReproOpen(!isNotReproOpen)}
            className="w-full p-5 bg-[#FAF9F5] flex items-center justify-between hover:bg-[#F0EEE6] transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <XCircle className="w-4 h-4 text-[#C4473A]" />
              <h4 className="font-semibold text-sm text-[#141413]">
                Not Reproduced Findings ({notReproBugs.length})
              </h4>
            </div>

            <div className="flex items-center gap-2 text-xs font-mono text-[#8A887F]">
              <span>Not counted as bugs</span>
              {isNotReproOpen ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </div>
          </button>

          {isNotReproOpen && (
            <div className="p-5 border-t border-[#E3DACC] space-y-2">
              {notReproBugs.length === 0 ? (
                <p className="text-xs text-[#8A887F] italic">
                  No unconfirmed findings.
                </p>
              ) : (
                notReproBugs.map((b) => (
                  <div
                    key={b.id}
                    className="p-3 rounded-xl border border-[#F2CAC5] bg-[#FAEBE9]/30 flex items-center justify-between gap-3"
                  >
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-2">
                        <Chip variant={b.severity} size="xs">
                          {b.severity}
                        </Chip>
                        <h5 className="font-semibold text-xs text-[#141413] truncate">
                          {b.title}
                        </h5>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <ReplayPips
                        replays={b.replays}
                        status={b.status}
                        bug={b}
                        size="sm"
                      />
                      <Link
                        href={`/results/${runId}/bugs/${b.id}`}
                        className="text-xs text-[#D97757] hover:underline font-medium inline-flex items-center gap-1"
                      >
                        <span>Evidence</span>
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* 6. REVIEW DECISION AUDIT LOG */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
        <h3 className="font-heading text-lg font-normal text-[#141413]">
          Review Gate Audit Log ({report.review_log.length})
        </h3>

        {report.review_log.length === 0 ? (
          <p className="text-xs text-[#8A887F] italic">
            No decisions logged during review gate.
          </p>
        ) : (
          <div className="divide-y divide-[#E3DACC]/50 max-h-60 overflow-y-auto">
            {report.review_log.map((log, idx) => (
              <div
                key={idx}
                className="py-2.5 flex items-center justify-between gap-3 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {log.actor === "reviewer_agent" ? (
                    <Bot className="w-4 h-4 text-[#D97757] shrink-0" />
                  ) : (
                    <User className="w-4 h-4 text-[#6B6A64] shrink-0" />
                  )}
                  <span className="font-medium text-[#141413]">
                    {log.actor === "reviewer_agent"
                      ? "Reviewer Agent"
                      : "Human Reviewer"}
                  </span>
                  <span className="text-[#8A887F]">•</span>
                  <span className="font-mono text-[#6B6A64]">
                    Test: {log.test_id}
                  </span>
                  {log.reason && (
                    <span className="text-[#8A887F] truncate italic">
                      &ldquo;{log.reason}&rdquo;
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Chip variant={log.decision} size="xs">
                    {log.decision}
                  </Chip>
                  <span className="text-[10px] text-[#8A887F] font-mono">
                    {formatRelativeTime(log.at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 7. HONEST NOTE STRIP */}
      <div className="p-4 rounded-xl bg-[#F0EEE6] border border-[#E3DACC] flex items-start gap-3">
        <Info className="w-5 h-5 text-[#D97757] shrink-0 mt-0.5" />
        <p className="text-xs text-[#6B6A64] leading-relaxed">
          <strong className="text-[#141413]">Honest QA Principle:</strong>{" "}
          Confirmed means reproduced in 3 of 3 deterministic replays. It does
          not mean the application has no other bugs. Findings that failed to
          reproduce (0/3) are preserved transparently above for engineering
          reference.
        </p>
      </div>
    </div>
  );
}
