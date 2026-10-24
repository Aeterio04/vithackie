"use client";

import React, { useState, useRef } from "react";
import Link from "next/link";
import { Sparkles, Lock, ExternalLink, Loader2, AlertCircle, ArrowRight } from "lucide-react";

interface AutoFixButtonProps {
  runId: string;
  bugId?: string;
  bugTitle?: string;
  projectId?: string;
  isConfigured: boolean;
  checkingReadiness?: boolean;
  launchingFix?: boolean;
  onLaunch: (bugId?: string) => void;
  onOpenModal: (bugId?: string) => void;
  variant?: "compact" | "primary" | "card";
  className?: string;
}

export function AutoFixButton({
  runId,
  bugId,
  bugTitle,
  projectId,
  isConfigured,
  checkingReadiness = false,
  launchingFix = false,
  onLaunch,
  onOpenModal,
  variant = "compact",
  className = "",
}: AutoFixButtonProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const hideTimerRef = useRef<NodeJS.Timeout | null>(null);

  const settingsUrl = projectId
    ? `/projects/${projectId}?tab=settings#github-integration`
    : "/projects";

  const handleMouseEnter = () => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (!isConfigured) {
      setShowTooltip(true);
    }
  };

  const handleMouseLeave = () => {
    hideTimerRef.current = setTimeout(() => {
      setShowTooltip(false);
    }, 250);
  };

  if (checkingReadiness) {
    return (
      <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E3DACC] bg-[#FAF9F5] text-xs font-mono text-[#8A887F] ${className}`}>
        <Loader2 className="w-3 h-3 animate-spin text-[#D97757]" />
        <span>Checking GitHub...</span>
      </div>
    );
  }

  // 1. CONFIG NOT READY (DISABLED BUTTON + HOVER POPOVER)
  if (!isConfigured) {
    return (
      <div
        className="relative inline-block"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <button
          type="button"
          disabled
          aria-disabled="true"
          className={`cursor-not-allowed select-none inline-flex items-center gap-1.5 rounded-lg border border-[#E3DACC] bg-[#FAF9F5]/80 text-[#8A887F] opacity-75 shadow-none transition-all ${
            variant === "compact"
              ? "px-2.5 py-1 text-xs font-medium"
              : "px-4 py-2 text-xs font-semibold"
          } ${className}`}
        >
          <Lock className="w-3 h-3 text-[#A1A09A]" />
          <span>Auto-Fix (PR)</span>
        </button>

        {/* Hover Popover with Message and Hyperlink */}
        {showTooltip && (
          <div
            className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-3.5 bg-[#18181B] text-white border border-[#27272A] rounded-xl shadow-2xl z-50 animate-in fade-in-0 zoom-in-95 pointer-events-auto"
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          >
            {/* Popover Arrow */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-[#18181B]" />

            <div className="flex items-center gap-1.5 text-amber-400 font-semibold text-xs mb-1.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>GitHub & PAT Required</span>
            </div>

            <p className="text-[11px] text-[#A1A1AA] leading-relaxed mb-3">
              To trigger autonomous verification replays and automatic PRs, connect your GitHub repository and PAT token.
            </p>

            <div className="pt-2 border-t border-[#27272A] flex items-center justify-between text-xs">
              <Link
                href={settingsUrl}
                className="text-[#D97757] hover:underline font-medium inline-flex items-center gap-1 group"
                onClick={(e) => e.stopPropagation()}
              >
                <span>Update in Settings</span>
                <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
              </Link>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowTooltip(false);
                  onOpenModal(bugId);
                }}
                className="text-[11px] text-[#D4D4D8] hover:text-white underline cursor-pointer"
              >
                Quick Connect
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // 2. CONFIG READY (ENABLED BUTTON)
  if (variant === "compact") {
    return (
      <button
        type="button"
        onClick={() => onLaunch(bugId)}
        disabled={launchingFix}
        className={`px-2.5 py-1 rounded-lg text-xs font-medium bg-white border border-[#D97757]/40 text-[#D97757] hover:bg-[#D97757] hover:text-white transition-all inline-flex items-center gap-1.5 shadow-2xs hover:shadow-xs active:scale-[0.98] cursor-pointer ${className}`}
        title={`Trigger autonomous Playwright replay, diff last commit, and generate PR for ${bugTitle || "defect"}`}
      >
        {launchingFix ? (
          <>
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>Starting Fix...</span>
          </>
        ) : (
          <>
            <Sparkles className="w-3 h-3" />
            <span>Auto-Fix (PR)</span>
          </>
        )}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onLaunch(bugId)}
      disabled={launchingFix}
      className={`px-4 py-2 rounded-xl text-xs font-semibold bg-[#D97757] hover:bg-[#C26243] text-white shadow-xs hover:shadow transition-all inline-flex items-center gap-2 active:scale-[0.98] cursor-pointer ${className}`}
      title="Run single verification check, inspect latest commit, and open PR"
    >
      {launchingFix ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span>Synthesizing Fix & PR...</span>
        </>
      ) : (
        <>
          <Sparkles className="w-3.5 h-3.5 fill-current" />
          <span>Launch AI Fix (Generate PR)</span>
        </>
      )}
    </button>
  );
}
