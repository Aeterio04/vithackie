"use client";

import React from "react";
import { StartTestForm } from "@/components/features/StartTestForm";
import { Check, X, Shield, Sparkles } from "lucide-react";

export default function StartPage() {
  return (
    <div className="space-y-8 pb-12 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="font-heading text-3xl font-normal text-[#141413]">
          Upload & Start Test Run
        </h1>
        <p className="text-xs text-[#6B6A64] mt-1">
          Specify target URL, upload feature specifications, configure budgets,
          and initialize the autonomous Explorer and Planner agents.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Main Form Column (8 cols) */}
        <div className="lg:col-span-8">
          <React.Suspense fallback={null}>
          <StartTestForm />
        </React.Suspense>
        </div>

        {/* Sidebar Cards (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          {/* V1 Scope Card */}
          <div className="bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-[0_1px_2px_rgba(20,20,19,0.05)] space-y-4">
            <div className="flex items-center gap-2 pb-3 border-b border-[#E3DACC]/60">
              <Shield className="w-4 h-4 text-[#D97757]" />
              <h3 className="font-heading text-base font-normal text-[#141413]">
                V1 Scope & Support
              </h3>
            </div>

            {/* Scope IN */}
            <div className="space-y-2">
              <span className="text-[11px] font-semibold text-[#5E8C61] uppercase tracking-wider block">
                In Scope (Supported)
              </span>
              <ul className="text-xs space-y-2 text-[#141413]">
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-[#5E8C61] shrink-0 mt-0.5" />
                  <span>Web GUI applications & SPAs</span>
                </li>
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-[#5E8C61] shrink-0 mt-0.5" />
                  <span>Staging, preview, and local targets</span>
                </li>
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-[#5E8C61] shrink-0 mt-0.5" />
                  <span>Chromium browser headless workers</span>
                </li>
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-[#5E8C61] shrink-0 mt-0.5" />
                  <span>3x Deterministic bug replay proof</span>
                </li>
              </ul>
            </div>

            {/* Scope OUT */}
            <div className="space-y-2 pt-3 border-t border-[#E3DACC]/60">
              <span className="text-[11px] font-semibold text-[#C4473A] uppercase tracking-wider block">
                Out of Scope (V1)
              </span>
              <ul className="text-xs space-y-2 text-[#6B6A64]">
                <li className="flex items-start gap-2">
                  <X className="w-4 h-4 text-[#C4473A] shrink-0 mt-0.5" />
                  <span>Native mobile iOS/Android apps</span>
                </li>
                <li className="flex items-start gap-2">
                  <X className="w-4 h-4 text-[#C4473A] shrink-0 mt-0.5" />
                  <span>CAPTCHA, Cloudflare bot challenges, & 2FA</span>
                </li>
                <li className="flex items-start gap-2">
                  <X className="w-4 h-4 text-[#C4473A] shrink-0 mt-0.5" />
                  <span>Live production environments (by policy)</span>
                </li>
                <li className="flex items-start gap-2">
                  <X className="w-4 h-4 text-[#C4473A] shrink-0 mt-0.5" />
                  <span>Unit or code-level testing</span>
                </li>
              </ul>
            </div>
          </div>

          {/* Architecture Card */}
          <div className="bg-[#F0EEE6] border border-[#E3DACC] rounded-[16px] p-5 space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[#141413]">
              <Sparkles className="w-4 h-4 text-[#D97757]" />
              <span>Deterministic Verification</span>
            </div>
            <p className="text-xs text-[#6B6A64] leading-relaxed">
              KAWACH will never report an LLM conjecture as a confirmed bug. Every
              suspected issue generates a typed Playwright script and is
              re-executed 3 times in isolated Docker containers before grading.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
