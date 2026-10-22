"use client";

import React from "react";
import { GitCommit, Sparkles, Shield, GitPullRequest } from "lucide-react";
import { Button } from "@/shared/ui/Button";

interface CommitEmptyStateProps {
  projectId: string;
}

export function CommitEmptyState({ projectId }: CommitEmptyStateProps) {
  return (
    <div className="bg-white border border-[#E3DACC] rounded-[16px] p-10 text-center max-w-xl mx-auto shadow-xs">
      <div className="w-14 h-14 rounded-2xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center mx-auto mb-4 text-[#D97757]">
        <GitCommit className="w-7 h-7" />
      </div>

      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium bg-[#FAF9F5] border border-[#E3DACC] text-[#D97757] mb-3">
        <Sparkles className="w-3.5 h-3.5" />
        Product Roadmap Feature (Phase 5 Scaffold)
      </span>

      <h2 className="font-heading text-2xl font-normal text-[#141413] mb-2">
        Commit Triggers & Auto-Fix Loop
      </h2>

      <p className="text-xs text-[#6B6A64] leading-relaxed mb-6">
        When linked with GitHub webhooks, KAWACH automatically triggers saved regression tests on every push.
        If a new commit causes a regression, KAWACH traces failure evidence back to code, computes probabilistic
        root cause rankings, and synthesizes unified diff patches.
      </p>

      <div className="bg-[#FAF9F5] border border-[#E3DACC] rounded-xl p-4 text-left mb-6 space-y-2">
        <div className="flex items-center gap-2 text-xs font-medium text-[#141413]">
          <GitPullRequest className="w-4 h-4 text-[#5E8C61]" />
          <span>Core Safety Invariants (Enforced in Code):</span>
        </div>
        <ul className="text-xs text-[#6B6A64] space-y-1.5 list-disc list-inside">
          <li><strong>Zero direct push:</strong> Auto-fix only opens Pull Requests, never pushes to main.</li>
          <li><strong>3x Verification Proof:</strong> Patches are validated with 3x replay trials before PR submission.</li>
          <li><strong>Small Fix Boundary:</strong> Auto-fix strictly restricted to single-file, &le;50 line patches; sensitive paths are escalated.</li>
        </ul>
      </div>

      <div className="flex items-center justify-center gap-3">
        <Button variant="secondary" onClick={() => window.history.back()}>
          Back to Overview
        </Button>
      </div>
    </div>
  );
}
