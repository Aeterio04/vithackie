"use client";

import React, { useState } from "react";
import { type Worker } from "@/types";
import { Chip } from "./Chip";
import { Monitor, Terminal, Clock, Maximize2, X } from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";

interface WorkerCardProps {
  worker: Worker;
  className?: string;
}

export function WorkerCard({ worker, className }: WorkerCardProps) {
  const [isZoomed, setIsZoomed] = useState(false);
  const isExploratory = worker.kind === "exploratory";
  const isActive = worker.status === "running" || worker.status === "verifying";

  const screenshotSrc = worker.latest_screenshot_url
    ? worker.screenshot_updated_at
      ? `${worker.latest_screenshot_url}?t=${encodeURIComponent(worker.screenshot_updated_at)}`
      : worker.latest_screenshot_url
    : null;

  return (
    <>
      <div
        className={`bg-white border rounded-[16px] p-4 shadow-[0_1px_2px_rgba(20,20,19,0.05)] flex flex-col justify-between transition-all ${
          isActive ? "border-[#D97757]/60 shadow-[0_0_0_1px_rgba(217,119,87,0.15)]" : "border-[#E3DACC]"
        } ${className || ""}`}
      >
        <div>
          {/* Worker Header */}
          <div className="flex items-center justify-between gap-2 pb-3 border-b border-[#E3DACC]/60">
            <div className="flex items-center gap-2">
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                  isActive ? "bg-orange-50 text-[#D97757] ring-2 ring-[#D97757]/20" : "bg-[#F0EEE6] text-[#6B6A64]"
                }`}
              >
                {isExploratory ? (
                  <Terminal className="w-4 h-4 text-[#D97757]" />
                ) : (
                  <Monitor className="w-4 h-4" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <h4 className="text-sm font-semibold text-[#141413]">
                    {isExploratory ? "Exploratory Crawler" : `Playwright Worker ${worker.id}`}
                  </h4>
                  {isActive && (
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  )}
                </div>
                <p className="text-[11px] font-mono text-[#8A887F]">Node: {worker.id}</p>
              </div>
            </div>

            <Chip variant={worker.status} dot size="xs">
              {worker.status}
            </Chip>
          </div>

          {/* Current Activity */}
          <div className="py-3 space-y-1.5">
            <div className="text-xs text-[#6B6A64] flex items-center gap-1.5">
              <span className="font-medium text-[#141413]">Active test:</span>
              <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-[#F0EEE6] text-[#141413] border border-[#E3DACC]">
                {worker.current_test_id || "None (idle)"}
              </span>
            </div>

            <div className="text-xs text-[#6B6A64] truncate">
              <span className="font-medium text-[#141413]">Ongoing Step: </span>
              <span className="text-[#6B6A64]" title={worker.current_step || undefined}>
                {worker.current_step || "Awaiting task..."}
              </span>
            </div>
          </div>
        </div>

        {/* Screen Preview Container */}
        <div className="mt-2 pt-2 border-t border-[#E3DACC]/40">
          <div
            onClick={() => screenshotSrc && setIsZoomed(true)}
            className={`relative aspect-video rounded-lg overflow-hidden bg-[#1E1E1C] flex items-center justify-center border border-[#E3DACC]/80 ${
              screenshotSrc ? "cursor-pointer group hover:border-[#D97757] transition-all" : ""
            }`}
          >
            {screenshotSrc ? (
              <>
                <img
                  src={screenshotSrc}
                  alt={`Worker ${worker.id} live viewport`}
                  className="w-full h-full object-cover group-hover:scale-102 transition-transform duration-200"
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs gap-1.5 font-medium">
                  <Maximize2 className="w-4 h-4" />
                  <span>Enlarge live capture</span>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center text-[#6B6A64] p-3 text-center">
                <Monitor className="w-6 h-6 mb-1 opacity-40 text-[#FAF9F5]" />
                <span className="text-[11px] font-mono text-[#8A887F]">
                  No screen capture yet
                </span>
              </div>
            )}

            {worker.screenshot_updated_at && (
              <div className="absolute bottom-1 right-1 bg-black/75 backdrop-blur-xs text-[#E5E3DC] text-[10px] px-1.5 py-0.5 rounded font-mono flex items-center gap-1 z-10">
                <Clock className="w-2.5 h-2.5 text-[#D97757]" />
                <span>{formatRelativeTime(worker.screenshot_updated_at)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Lightbox Zoom Modal */}
      {isZoomed && screenshotSrc && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setIsZoomed(false)}
        >
          <div
            className="relative max-w-4xl w-full bg-[#1E1E1C] rounded-2xl overflow-hidden border border-[#E3DACC]/30 shadow-2xl space-y-2 p-2"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-3 py-2 text-white">
              <div className="flex items-center gap-2">
                <Monitor className="w-4 h-4 text-[#D97757]" />
                <span className="text-sm font-semibold">
                  Worker {worker.id} — Live Browser Viewport
                </span>
                {worker.current_test_id && (
                  <span className="text-xs font-mono text-[#D97757] bg-white/10 px-2 py-0.5 rounded">
                    {worker.current_test_id}
                  </span>
                )}
              </div>
              <button
                onClick={() => setIsZoomed(false)}
                className="text-zinc-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="rounded-xl overflow-hidden bg-black aspect-video flex items-center justify-center">
              <img
                src={screenshotSrc}
                alt={`Worker ${worker.id} live viewport`}
                className="w-full h-full object-contain"
              />
            </div>
            {worker.current_step && (
              <p className="text-xs text-zinc-300 px-3 py-1 font-mono">
                Step: {worker.current_step}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
