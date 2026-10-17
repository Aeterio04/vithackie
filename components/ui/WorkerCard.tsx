import React from "react";
import { type Worker } from "@/types";
import { Chip } from "./Chip";
import { Monitor, Terminal, Clock } from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";

interface WorkerCardProps {
  worker: Worker;
  className?: string;
}

export function WorkerCard({ worker, className }: WorkerCardProps) {
  const isExploratory = worker.kind === "exploratory";

  return (
    <div
      className={`bg-white border border-[#E3DACC] rounded-[16px] p-4 shadow-[0_1px_2px_rgba(20,20,19,0.05)] flex flex-col justify-between ${className || ""}`}
    >
      <div>
        {/* Worker Header */}
        <div className="flex items-center justify-between gap-2 pb-3 border-b border-[#E3DACC]/60">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[#F0EEE6] flex items-center justify-center text-[#6B6A64]">
              {isExploratory ? (
                <Terminal className="w-4 h-4 text-[#D97757]" />
              ) : (
                <Monitor className="w-4 h-4 text-[#6B6A64]" />
              )}
            </div>
            <div>
              <h4 className="text-sm font-semibold text-[#141413]">
                {isExploratory ? "Exploratory Tester" : `Worker ${worker.id}`}
              </h4>
              <p className="text-[11px] font-mono text-[#8A887F]">{worker.id}</p>
            </div>
          </div>

          <Chip variant={worker.status} dot size="xs">
            {worker.status}
          </Chip>
        </div>

        {/* Current Activity */}
        <div className="py-3 space-y-1">
          <div className="text-xs text-[#6B6A64]">
            <span className="font-medium text-[#141413]">Current test: </span>
            <span className="font-mono text-[#141413]">
              {worker.current_test_id || "None (idle)"}
            </span>
          </div>

          <div className="text-xs text-[#6B6A64] truncate">
            <span className="font-medium text-[#141413]">Step: </span>
            <span className="text-[#6B6A64]">
              {worker.current_step || "Awaiting task..."}
            </span>
          </div>
        </div>
      </div>

      {/* Screen Preview Container */}
      <div className="mt-2 pt-2 border-t border-[#E3DACC]/40">
        <div className="relative aspect-video rounded-lg overflow-hidden bg-[#1E1E1C] flex items-center justify-center border border-[#E3DACC]/80">
          {worker.latest_screenshot_url ? (
            /* Plain <img> as specified in requirements (not next/image) */
            <img
              src={worker.latest_screenshot_url}
              alt={`Worker ${worker.id} screenshot`}
              className="w-full h-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex flex-col items-center justify-center text-[#6B6A64] p-3 text-center">
              <Monitor className="w-6 h-6 mb-1 opacity-40 text-[#FAF9F5]" />
              <span className="text-[11px] font-mono text-[#8A887F]">
                No screen capture yet
              </span>
            </div>
          )}

          {worker.screenshot_updated_at && (
            <div className="absolute bottom-1 right-1 bg-black/70 backdrop-blur-xs text-[#E5E3DC] text-[10px] px-1.5 py-0.5 rounded font-mono flex items-center gap-1">
              <Clock className="w-2.5 h-2.5" />
              <span>{formatRelativeTime(worker.screenshot_updated_at)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
