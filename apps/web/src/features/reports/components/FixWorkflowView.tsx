"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { fixesApi, FixSession } from "@/features/fixes/api";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  ShieldCheck,
  GitCommit,
  Sparkles,
  GitPullRequest,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ExternalLink,
  ArrowLeft,
  Terminal,
  RefreshCw,
  Copy,
  Check,
  FileCode,
  Clock,
  ChevronRight,
  Loader2,
  AlertCircle,
} from "lucide-react";

function GithubIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

export function FixWorkflowView() {
  const params = useParams();
  const runId = params.runId as string;
  const fixId = params.fixId as string;
  const router = useRouter();

  const [session, setSession] = useState<FixSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedPr, setCopiedPr] = useState(false);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const logBottomRef = useRef<HTMLDivElement>(null);

  // Poll fix session until terminal state
  useEffect(() => {
    let timer: NodeJS.Timeout;

    const fetchStatus = async () => {
      try {
        const data = await fixesApi.getFixStatus(fixId);
        setSession(data);
        setError(null);

        // Check if still active
        const terminalStatuses = [
          "pr_opened",
          "pr_exists",
          "dry_run_ready",
          "not_reproduced",
          "flaky",
          "no_editable_changes",
          "fix_not_possible",
          "github_error",
          "failed",
        ];

        if (!terminalStatuses.includes(data.status)) {
          timer = setTimeout(fetchStatus, 1500);
        }
      } catch (err: any) {
        setError(err.message || "Failed to load fix status.");
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [fixId]);

  // Auto-scroll log console
  useEffect(() => {
    logBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.logs?.length]);

  if (loading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto pb-20 pt-4">
        <Skeleton className="h-28 w-full rounded-2xl" />
        <Skeleton className="h-20 w-full rounded-2xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-64 w-full rounded-2xl" />
          <Skeleton className="h-64 w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="max-w-xl mx-auto my-16 p-8 bg-white border border-[#E3DACC] rounded-2xl shadow-xs text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-[#FAEBE9] border border-[#F2CAC5] text-[#C4473A] flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-heading text-[#141413]">Fix Pipeline Not Found</h2>
        <p className="text-xs text-[#6B6A64]">
          {error || `No active fix session was found with identifier ${fixId}.`}
        </p>
        <Button variant="secondary" size="sm" onClick={() => router.push(`/reports/${runId}`)}>
          Back to Report
        </Button>
      </div>
    );
  }

  const isCompleted = [
    "pr_opened",
    "pr_exists",
    "dry_run_ready",
    "not_reproduced",
    "flaky",
    "no_editable_changes",
    "fix_not_possible",
    "failed",
  ].includes(session.status);

  const isSuccessPr = session.status === "pr_opened" || session.status === "pr_exists";

  const copyToClipboard = (text: string, setCopied: (v: boolean) => void) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-24 pt-2">
      {/* 1. NAVIGATION & TOP BREADCRUMB */}
      <div className="flex items-center justify-between gap-4">
        <Link
          href={`/reports/${runId}`}
          className="inline-flex items-center gap-1.5 text-xs text-[#6B6A64] hover:text-[#141413] transition-colors font-medium"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Verification Report</span>
        </Link>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-[#8A887F]">Session: {fixId}</span>
          {!isCompleted && (
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#D97757] opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#D97757]" />
            </span>
          )}
        </div>
      </div>

      {/* 2. MAIN HEADER CARD */}
      <div className="bg-white border border-[#E3DACC] rounded-[20px] p-6 shadow-xs space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-0.5 text-xs font-semibold rounded-md bg-[#FAF9F5] border border-[#E3DACC] text-[#6B6A64]">
                Autonomous Fix Pipeline
              </span>
              <span className="text-xs font-mono text-[#8A887F]">
                Run #{runId}
              </span>
              {session.bugId && (
                <span className="text-xs font-mono text-[#8A887F]">
                  • Defect #{session.bugId}
                </span>
              )}
            </div>

            <h1 className="font-heading text-2xl font-normal text-[#141413]">
              {session.bugTitle || "Automated Repair & PR Synthesis"}
            </h1>

            <div className="flex flex-wrap items-center gap-3 text-xs text-[#6B6A64] pt-0.5">
              <span className="inline-flex items-center gap-1.5 font-mono text-[#141413]">
                <GithubIcon className="w-3.5 h-3.5 text-[#8A887F]" />
                <a
                  href={`https://github.com/${session.repo}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-[#D97757] hover:underline"
                >
                  {session.repo}
                </a>
              </span>
              <span>•</span>
              <span className="font-mono text-[#8A887F]">Base: main</span>
              <span>•</span>
              <span className="font-mono text-[#8A887F]">Target: {session.targetUrl}</span>
            </div>
          </div>

          <div className="shrink-0 flex flex-col items-start md:items-end gap-1.5">
            <div className="flex items-center gap-2">
              <Chip
                variant={
                  isSuccessPr
                    ? "confirmed"
                    : session.status === "failed" || session.status === "not_reproduced"
                    ? "not_reproduced"
                    : session.status === "flaky" || session.status === "fix_not_possible"
                    ? "flaky"
                    : "verifying"
                }
                size="sm"
              >
                {session.status.replace(/_/g, " ").toUpperCase()}
              </Chip>
            </div>
            <span className="text-[11px] text-[#8A887F] font-mono">
              Step: {session.stage.toUpperCase()} ({session.progress}%)
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1.5 pt-1">
          <div className="w-full bg-[#FAF9F5] border border-[#E3DACC]/60 h-2 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 rounded-full ${
                isSuccessPr
                  ? "bg-[#5E8C61]"
                  : session.status === "failed"
                  ? "bg-[#C4473A]"
                  : "bg-[#D97757]"
              }`}
              style={{ width: `${session.progress}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-[11px] font-mono text-[#8A887F]">
            <span className="truncate max-w-xl text-[#141413] font-medium flex items-center gap-1.5">
              {!isCompleted && <Loader2 className="w-3 h-3 animate-spin text-[#D97757]" />}
              {session.currentStep}
            </span>
            <span>{session.progress}%</span>
          </div>
        </div>
      </div>

      {/* 3. GRAND CELEBRATION PR BANNER IF PR WAS OPENED */}
      {isSuccessPr && session.pullRequest && (
        <div className="p-6 rounded-[20px] border border-[#D2E3D3] bg-gradient-to-r from-[#EBF2EB] to-[#FAF9F5] shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5 animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-[#5E8C61] text-white flex items-center justify-center shadow-xs">
                <GitPullRequest className="w-4 h-4" />
              </div>
              <h3 className="text-lg font-heading font-medium text-[#141413]">
                Autonomous Pull Request #{session.pullRequest.number} Created!
              </h3>
            </div>
            <p className="text-xs text-[#47704A] font-mono leading-relaxed">
              Branch: <span className="font-semibold text-[#141413]">{session.pullRequest.branch}</span> targeting <span className="font-semibold text-[#141413]">main</span>
            </p>
            <p className="text-xs text-[#6B6A64]">
              {session.pullRequest.title}
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => copyToClipboard(session.pullRequest?.url || "", setCopiedPr)}
              className="gap-1.5 text-xs bg-white"
            >
              {copiedPr ? <Check className="w-3.5 h-3.5 text-[#5E8C61]" /> : <Copy className="w-3.5 h-3.5 text-[#8A887F]" />}
              <span>{copiedPr ? "Copied Link" : "Copy PR URL"}</span>
            </Button>

            <a
              href={session.pullRequest.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#5E8C61] hover:bg-[#4E7650] text-white text-xs font-medium shadow-xs transition-colors"
            >
              <span>View PR on GitHub</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      )}

      {/* 4. FOUR-NODE WORKFLOW PIPELINE GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* NODE 1: DEFECT VERIFICATION */}
        <div className="bg-white border border-[#E3DACC] rounded-[18px] p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2.5 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#141413]">
                <ShieldCheck className="w-4 h-4 text-[#D97757]" />
              </div>
              <div>
                <h4 className="text-xs font-semibold text-[#141413]">Step 1: Verification (1 Run)</h4>
                <p className="text-[10px] text-[#8A887F]">Rule out test flakiness in sandbox</p>
              </div>
            </div>
            {session.verification ? (
              <Chip
                variant={session.verification.verdict === "confirmed" ? "confirmed" : "flaky"}
                size="xs"
              >
                {session.verification.verdict.toUpperCase()}
              </Chip>
            ) : session.stage === "verifier" ? (
              <span className="text-[11px] font-mono text-[#D97757] flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Verifying...
              </span>
            ) : (
              <span className="text-[11px] font-mono text-[#8A887F]">Queued</span>
            )}
          </div>

          {session.verification ? (
            <div className="space-y-2 text-xs">
              <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC]/60 space-y-1.5 font-mono">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-[#6B6A64]">Verification Outcome:</span>
                  <span className="font-semibold text-[#141413]">
                    {session.verification.failures}/1 Replays Failed
                  </span>
                </div>
                {session.verification.runs?.[0] && (
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-[#6B6A64]">Sandbox Duration:</span>
                    <span className="text-[#141413]">
                      {session.verification.runs[0].duration_ms} ms
                    </span>
                  </div>
                )}
              </div>

              {session.verification.observed_error && (
                <div className="space-y-1">
                  <span className="text-[10px] font-semibold text-[#C4473A] uppercase tracking-wider block">
                    Observed Assertion Failure
                  </span>
                  <div className="p-2.5 rounded-lg bg-[#FAEBE9] border border-[#F2CAC5] text-[#C4473A] font-mono text-[11px] leading-tight break-all max-h-24 overflow-y-auto">
                    {session.verification.observed_error}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-[#8A887F] italic py-3">
              Running isolated Playwright test in sandbox environment...
            </p>
          )}
        </div>

        {/* NODE 2: COMMIT CONTEXT */}
        <div className="bg-white border border-[#E3DACC] rounded-[18px] p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2.5 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#141413]">
                <GitCommit className="w-4 h-4 text-[#D97757]" />
              </div>
              <div>
                <h4 className="text-xs font-semibold text-[#141413]">Step 2: Commit Context</h4>
                <p className="text-[10px] text-[#8A887F]">Extract diff from origin/main</p>
              </div>
            </div>
            {session.commitContext ? (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#EBF2EB] text-[#47704A] border border-[#D2E3D3] font-semibold">
                PINNED
              </span>
            ) : session.stage === "collector" ? (
              <span className="text-[11px] font-mono text-[#D97757] flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Querying API...
              </span>
            ) : (
              <span className="text-[11px] font-mono text-[#8A887F]">Pending</span>
            )}
          </div>

          {session.commitContext ? (
            <div className="space-y-2 text-xs">
              <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC]/60 space-y-1.5 font-mono text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-[#6B6A64]">Latest SHA:</span>
                  <span className="font-semibold text-[#D97757]">
                    {(
                      session.commitContext.sha ||
                      session.commitContext.summary?.sha ||
                      "Pinned"
                    ).slice(0, 7)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[#6B6A64]">Author:</span>
                  <span className="text-[#141413] truncate max-w-[200px]">
                    {session.commitContext.author ||
                      session.commitContext.summary?.author ||
                      "GitHub Author"}
                  </span>
                </div>
                <div className="pt-1 border-t border-[#E3DACC]/40">
                  <span className="text-[#6B6A64] block text-[10px] uppercase">Message</span>
                  <p className="text-[#141413] line-clamp-1 italic">
                    "{session.commitContext.message ||
                      session.commitContext.summary?.message ||
                      "Latest commit on main"}"
                  </p>
                </div>
              </div>

              {session.commitContext.files && session.commitContext.files.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[10px] font-semibold text-[#6B6A64] uppercase tracking-wider block">
                    Files In Commit ({session.commitContext.files.length})
                  </span>
                  <div className="max-h-24 overflow-y-auto space-y-1 pr-1">
                    {session.commitContext.files.map((f, idx) => (
                      <div
                        key={idx}
                        className="px-2 py-1 rounded bg-[#FAF9F5] border border-[#E3DACC] font-mono text-[10px] flex items-center justify-between"
                      >
                        <span className="truncate max-w-[220px] text-[#141413]">
                          {f.filename || f.path || "Modified file"}
                        </span>
                        <span className="text-[#5E8C61]">
                          +{f.additions ?? 1}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-[#8A887F] italic py-3">
              Awaiting verification completion before querying GitHub...
            </p>
          )}
        </div>

        {/* NODE 3: FIX LLM SYNTHESIS */}
        <div className="bg-white border border-[#E3DACC] rounded-[18px] p-5 shadow-xs space-y-3 md:col-span-2">
          <div className="flex items-center justify-between pb-2.5 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#141413]">
                <Sparkles className="w-4 h-4 text-[#D97757]" />
              </div>
              <div>
                <h4 className="text-xs font-semibold text-[#141413]">Step 3: Fix Synthesis (LLM)</h4>
                <p className="text-[10px] text-[#8A887F]">
                  Exact search-and-replace patch with prompt-injection containment
                </p>
              </div>
            </div>
            {session.proposal ? (
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#EBF2EB] text-[#47704A] border border-[#D2E3D3] font-semibold">
                CONFIDENCE {Math.round(session.proposal.confidence * 100)}%
              </span>
            ) : session.stage === "llm" ? (
              <span className="text-[11px] font-mono text-[#D97757] flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Synthesizing with Groq...
              </span>
            ) : (
              <span className="text-[11px] font-mono text-[#8A887F]">Pending</span>
            )}
          </div>

          {session.proposal ? (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC]/60 space-y-1 md:col-span-2">
                  <span className="text-[10px] font-semibold text-[#6B6A64] uppercase tracking-wider block">
                    Root Cause Analysis
                  </span>
                  <p className="text-[#141413] leading-relaxed">
                    {session.proposal.root_cause}
                  </p>
                  <p className="text-[11px] text-[#8A887F] pt-1">
                    {session.proposal.explanation}
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC]/60 space-y-2">
                  <span className="text-[10px] font-semibold text-[#6B6A64] uppercase tracking-wider block">
                    Proposed PR Details
                  </span>
                  <div className="text-[11px] font-mono text-[#141413] font-medium truncate">
                    {session.proposal.pr_title}
                  </div>
                  <div className="text-[10px] font-mono text-[#5E8C61]">
                    {session.proposal.edits?.length || 0} file edit(s) validated
                  </div>
                </div>
              </div>

              {/* Exact Search and Replace Diffs */}
              {session.proposal.edits?.map((edit, idx) => (
                <div key={idx} className="rounded-xl border border-[#E3DACC] overflow-hidden bg-[#1E1E1C]">
                  <div className="px-3.5 py-1.5 bg-[#141413] border-b border-[#2C2C2A] flex items-center justify-between text-[11px] font-mono text-[#A1A1AA]">
                    <span className="text-[#FAF9F5] font-semibold">{edit.path}</span>
                    <span className="text-[10px] text-[#71717A]">Targeted Search & Replace</span>
                  </div>
                  <div className="p-3 font-mono text-[11px] space-y-2 overflow-x-auto">
                    <div className="p-2 rounded bg-[#C4473A]/15 border border-[#C4473A]/30 text-[#F87171]">
                      <span className="text-[9px] uppercase tracking-wider font-bold block text-[#FCA5A5] mb-1">
                        - Search String (Exact match in commit)
                      </span>
                      <pre className="whitespace-pre-wrap">{edit.old_str}</pre>
                    </div>
                    <div className="p-2 rounded bg-[#5E8C61]/15 border border-[#5E8C61]/30 text-[#4ADE80]">
                      <span className="text-[9px] uppercase tracking-wider font-bold block text-[#86EFAC] mb-1">
                        + Replacement String
                      </span>
                      <pre className="whitespace-pre-wrap">{edit.new_str}</pre>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-[#8A887F] italic py-3">
              LLM repair synthesis will run once commit diff context is retrieved from GitHub...
            </p>
          )}
        </div>
      </div>

      {/* 5. LIVE ACTIVITY TERMINAL LOG VIEWER */}
      <div className="bg-[#18181B] border border-[#27272A] rounded-[20px] shadow-lg overflow-hidden">
        <div className="px-4 py-2.5 bg-[#121214] border-b border-[#27272A] flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-mono text-[#A1A1AA]">
            <Terminal className="w-3.5 h-3.5 text-[#D97757]" />
            <span className="font-semibold text-white">Live Execution Terminal</span>
            <span className="text-[10px] text-[#71717A]">({session.logs?.length || 0} events)</span>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              copyToClipboard(
                session.logs?.map((l) => `[${l.timestamp}] ${l.message}`).join("\n") || "",
                setCopiedLogs
              )
            }
            className="text-[10px] h-6 px-2 gap-1 bg-[#1E1E22] border-[#2E2E34] text-[#A1A1AA] hover:text-white"
          >
            {copiedLogs ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            <span>{copiedLogs ? "Copied" : "Copy Logs"}</span>
          </Button>
        </div>

        <div className="p-4 font-mono text-[11px] leading-relaxed max-h-64 overflow-y-auto space-y-1.5 scrollbar-thin scrollbar-thumb-zinc-700">
          {session.logs?.map((log, idx) => (
            <div key={idx} className="flex items-start gap-2 text-zinc-300">
              <span className="text-zinc-500 shrink-0 select-none">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span
                className={`px-1.5 py-0.2 rounded text-[10px] uppercase font-bold shrink-0 ${
                  log.level === "success"
                    ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/60"
                    : log.level === "error"
                    ? "bg-rose-950/80 text-rose-400 border border-rose-800/60"
                    : log.level === "warning"
                    ? "bg-amber-950/80 text-amber-400 border border-amber-800/60"
                    : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                }`}
              >
                {log.level}
              </span>
              <span className="text-zinc-200 break-words">{log.message}</span>
            </div>
          ))}
          <div ref={logBottomRef} />
        </div>
      </div>
    </div>
  );
}
