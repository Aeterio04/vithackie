"use client";

import React from "react";
import Link from "next/link";
import { Sparkles, ShieldCheck, GitCommit, FileCode2, GitPullRequest, ArrowRight, ExternalLink, CheckCircle2, AlertTriangle } from "lucide-react";
import { AutoFixButton } from "./AutoFixButton";

interface AutonomousFixCardProps {
  runId: string;
  projectId?: string;
  isConfigured: boolean;
  checkingReadiness: boolean;
  repo?: string;
  topBug?: {
    id: string;
    title: string;
    actual?: string;
    severity?: string;
  };
  launchingFix: boolean;
  onLaunch: (bugId?: string) => void;
  onOpenModal: (bugId?: string) => void;
}

export function AutonomousFixCard({
  runId,
  projectId,
  isConfigured,
  checkingReadiness,
  repo,
  topBug,
  launchingFix,
  onLaunch,
  onOpenModal,
}: AutonomousFixCardProps) {
  const settingsUrl = projectId
    ? `/projects/${projectId}?tab=settings#github-integration`
    : "/projects";

  return (
    <div className="bg-white border border-[#E3DACC] rounded-[20px] p-6 shadow-xs space-y-5">
      {/* 1. Header & Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#E3DACC]/60">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#D97757] shrink-0 shadow-2xs">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-heading text-lg font-normal text-[#141413]">
                Autonomous Defect Remediation & PR Pipeline
              </h3>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase bg-[#F0EEE6] text-[#6B6A64] border border-[#E3DACC]">
                1-Run Verifier + AI PR
              </span>
            </div>
            <p className="text-xs text-[#6B6A64] mt-0.5 max-w-2xl leading-relaxed">
              Kawach automatically isolates verified defects, checks the last commit on <code className="px-1 py-0.2 rounded bg-[#FAF9F5] text-[#141413] font-mono text-[11px]">origin/main</code>, synthesizes a targeted search-and-replace fix using LLM, and raises a ready-to-merge Pull Request.
            </p>
          </div>
        </div>

        {/* Integration Status Badge */}
        <div className="shrink-0 flex items-center gap-2.5">
          {isConfigured ? (
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 rounded-full text-xs font-mono bg-[#EBF2EB] border border-[#D2E3D3] text-[#47704A] inline-flex items-center gap-1.5 font-medium">
                <span className="w-2 h-2 rounded-full bg-[#5E8C61] animate-pulse" />
                <span>GitHub: {repo || "Connected"}</span>
              </span>
              <Link
                href={settingsUrl}
                className="text-xs text-[#8A887F] hover:text-[#141413] hover:underline"
                title="Manage repository & PAT token in Project Settings"
              >
                Settings
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 rounded-full text-xs font-mono bg-[#FAEBE9] border border-[#F2CAC5] text-[#C4473A] inline-flex items-center gap-1.5 font-medium">
                <span className="w-2 h-2 rounded-full bg-[#C4473A]" />
                <span>GitHub Setup Required</span>
              </span>
              <Link
                href={settingsUrl}
                className="text-xs text-[#D97757] hover:underline font-semibold inline-flex items-center gap-0.5"
              >
                <span>Link in Settings</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* 2. Pipeline Explanation Ribbon */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[#141413]">
            <ShieldCheck className="w-3.5 h-3.5 text-[#5E8C61]" />
            <span>1. Single Replay Check</span>
          </div>
          <p className="text-[11px] text-[#6B6A64] leading-relaxed">
            Replays reproduction script once in an isolated sandbox. Confirms error and advances immediately.
          </p>
        </div>

        <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[#141413]">
            <GitCommit className="w-3.5 h-3.5 text-[#2E78B7]" />
            <span>2. Last Commit Diff</span>
          </div>
          <p className="text-[11px] text-[#6B6A64] leading-relaxed">
            Inspects the latest commit on <code className="font-mono text-[10px]">origin/main</code> to detect the regression culprit.
          </p>
        </div>

        <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[#141413]">
            <FileCode2 className="w-3.5 h-3.5 text-[#D97757]" />
            <span>3. LLM Repair Synthesis</span>
          </div>
          <p className="text-[11px] text-[#6B6A64] leading-relaxed">
            LLM generates minimal search-and-replace fix patch with strict syntax validation.
          </p>
        </div>

        <div className="p-3 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[#141413]">
            <GitPullRequest className="w-3.5 h-3.5 text-[#6D28D9]" />
            <span>4. Automated PR</span>
          </div>
          <p className="text-[11px] text-[#6B6A64] leading-relaxed">
            Creates branch <code className="font-mono text-[10px]">kawach/fix-&lt;sha&gt;</code> and raises Pull Request on your repo.
          </p>
        </div>
      </div>

      {/* 3. Target Defect & Action Footer */}
      {topBug && (
        <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#FAF9F5]/60 p-4 rounded-xl border border-[#E3DACC]">
          <div className="space-y-0.5 min-w-0">
            <span className="text-[10px] uppercase font-mono tracking-wider font-semibold text-[#8A887F] block">
              Top Priority Confirmed Defect
            </span>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-[#D97757]">
                {topBug.id}
              </span>
              <p className="text-xs font-medium text-[#141413] truncate max-w-md">
                {topBug.title}
              </p>
            </div>
            {topBug.actual && (
              <p className="text-[11px] text-[#6B6A64] truncate max-w-lg">
                Observed: {topBug.actual}
              </p>
            )}
          </div>

          <div className="shrink-0 flex items-center gap-3">
            <AutoFixButton
              runId={runId}
              bugId={topBug.id}
              bugTitle={topBug.title}
              projectId={projectId}
              isConfigured={isConfigured}
              checkingReadiness={checkingReadiness}
              launchingFix={launchingFix}
              onLaunch={onLaunch}
              onOpenModal={onOpenModal}
              variant="primary"
            />
          </div>
        </div>
      )}
    </div>
  );
}
