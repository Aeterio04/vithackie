"use client";

import React from "react";
import { Bookmark, Sparkles, Shield, ArrowRight } from "lucide-react";
import { Button } from "@/shared/ui/Button";

interface SavedTestEmptyStateProps {
  projectId: string;
}

export function SavedTestEmptyState({ projectId }: SavedTestEmptyStateProps) {
  return (
    <div className="bg-white border border-[#E3DACC] rounded-[16px] p-10 text-center max-w-xl mx-auto shadow-xs">
      <div className="w-14 h-14 rounded-2xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center mx-auto mb-4 text-[#D97757]">
        <Bookmark className="w-7 h-7" />
      </div>

      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium bg-[#FAF9F5] border border-[#E3DACC] text-[#D97757] mb-3">
        <Sparkles className="w-3.5 h-3.5" />
        Product Roadmap Feature (Phase 5 Scaffold)
      </span>

      <h2 className="font-heading text-2xl font-normal text-[#141413] mb-2">
        Saved Test Library
      </h2>

      <p className="text-xs text-[#6B6A64] leading-relaxed mb-6">
        The Saved Test Library enables persistent regression suites. After executing test runs,
        verified defect reproductions and passing user journeys can be saved directly to your project.
        Upcoming releases will automate diff-aware test selection on every commit.
      </p>

      <div className="bg-[#FAF9F5] border border-[#E3DACC] rounded-xl p-4 text-left mb-6 space-y-2">
        <div className="flex items-center gap-2 text-xs font-medium text-[#141413]">
          <Shield className="w-4 h-4 text-[#5E8C61]" />
          <span>Planned Capabilities:</span>
        </div>
        <ul className="text-xs text-[#6B6A64] space-y-1.5 list-disc list-inside">
          <li>Diff-aware regression selection (run only tests touching modified components)</li>
          <li>Full suite vs fast PR test categorization</li>
          <li>Playwright TypeScript export & CI/CD synchronization</li>
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
