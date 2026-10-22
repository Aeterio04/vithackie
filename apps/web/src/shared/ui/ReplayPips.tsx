import React from "react";
import { cn } from "@/lib/utils";
import { type Replay, type BugStatus, verifyReplayStatus, Bug } from "@/types";
import { AlertTriangle } from "lucide-react";

interface ReplayPipsProps {
  replays?: Replay[];
  status?: BugStatus;
  showCaption?: boolean;
  showMismatchWarning?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  bug?: Bug;
}

export function ReplayPips({
  replays = [],
  status,
  showCaption = true,
  showMismatchWarning = true,
  size = "md",
  className,
  bug,
}: ReplayPipsProps) {
  // 3 deterministic replays
  const replaySlots = [1, 2, 3].map((slotIdx) => {
    return replays.find((r) => r.index === slotIdx);
  });

  const reproducedCount = replays.filter((r) => r.result === "reproduced").length;
  const completedCount = replays.filter(
    (r) => r.result === "reproduced" || r.result === "not_reproduced"
  ).length;

  const mismatchInfo = bug
    ? verifyReplayStatus(bug)
    : status
    ? verifyReplayStatus({
        id: "",
        title: "",
        severity: "medium",
        source: "test_runner",
        spec_item_ids: [],
        status,
        replays,
        steps_to_reproduce: [],
        expected: "",
        actual: "",
      })
    : null;

  const pipSizes = {
    sm: "w-2 h-2",
    md: "w-2.5 h-2.5",
    lg: "w-3.5 h-3.5",
  };

  return (
    <div className={cn("inline-flex items-center gap-2", className)}>
      <div className="flex items-center gap-1">
        {replaySlots.map((replay, idx) => {
          let pipColor = "bg-[#D9D4C7]"; // empty/pending grey
          let pipTitle = `Replay ${idx + 1}: pending`;

          if (replay) {
            if (replay.result === "reproduced") {
              pipColor = "bg-[#5E8C61]"; // Green / Reproduced
              pipTitle = `Replay ${idx + 1}: reproduced (${replay.duration_ms ? `${replay.duration_ms}ms` : "ok"})`;
            } else if (replay.result === "not_reproduced") {
              pipColor = "bg-[#C4473A]"; // Red / Not reproduced
              pipTitle = `Replay ${idx + 1}: not reproduced`;
            } else if (replay.result === "pending") {
              pipColor = "bg-[#D4A02A] animate-pulse";
              pipTitle = `Replay ${idx + 1}: in progress`;
            } else if (replay.result === "error") {
              pipColor = "bg-[#8A887F]";
              pipTitle = `Replay ${idx + 1}: execution error`;
            }
          }

          return (
            <div
              key={idx}
              title={pipTitle}
              className={cn("rounded-full transition-colors", pipSizes[size], pipColor)}
            />
          );
        })}
      </div>

      {showCaption && (
        <span className="text-xs font-mono text-[#6B6A64]">
          {completedCount === 0 && status === "suspected" ? (
            "Not yet verified"
          ) : (
            `${reproducedCount}/3`
          )}
        </span>
      )}

      {showMismatchWarning && mismatchInfo?.hasMismatch && (
        <span
          title={`Status mismatch: Bug is marked "${status}", but deterministic replays tally is ${reproducedCount}/${completedCount} reproduced.`}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-[#C4473A] bg-[#FAEBE9] border border-[#F2CAC5] px-1.5 py-0.5 rounded"
        >
          <AlertTriangle className="w-3 h-3 text-[#C4473A] shrink-0" />
          Status mismatch
        </span>
      )}
    </div>
  );
}
