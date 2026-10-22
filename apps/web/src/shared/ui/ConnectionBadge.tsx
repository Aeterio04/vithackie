import React from "react";
import { cn } from "@/lib/utils";
import { type ConnectionState } from "@/hooks/useRunStream";

interface ConnectionBadgeProps {
  state: ConnectionState;
  className?: string;
}

export function ConnectionBadge({ state, className }: ConnectionBadgeProps) {
  let label = "Disconnected";
  let dotClass = "bg-[#8A887F]";
  let badgeClass = "bg-[#F2F1EE] text-[#6B6A64] border-[#E3DACC]";

  if (state === "live") {
    label = "Live";
    dotClass = "bg-[#5E8C61] animate-pulse";
    badgeClass = "bg-[#EBF2EB] text-[#47704A] border-[#D2E3D3]";
  } else if (state === "reconnecting") {
    label = "Reconnecting...";
    dotClass = "bg-[#D4A02A] animate-ping";
    badgeClass = "bg-[#FBF4E6] text-[#A67319] border-[#F4E2BD]";
  } else if (state === "polling") {
    label = "Polling (fallback)";
    dotClass = "bg-[#D97757]";
    badgeClass = "bg-[#F6EDE8] text-[#C15F3C] border-[#F0D5C9]";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium border select-none",
        badgeClass,
        className
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", dotClass)} />
      <span>{label}</span>
    </span>
  );
}
