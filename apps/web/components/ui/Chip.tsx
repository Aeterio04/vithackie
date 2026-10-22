import React from "react";
import { cn } from "@/lib/utils";

export type ChipVariant =
  | "confirmed"
  | "passed"
  | "flaky"
  | "not_reproduced"
  | "failed"
  | "suspected"
  | "verifying"
  | "queued"
  | "running"
  | "pending"
  | "approved"
  | "rejected"
  | "skipped"
  | "error"
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "neutral"
  | "clay";

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant | string;
  size?: "xs" | "sm" | "md";
  dot?: boolean;
}

export function Chip({
  className,
  variant = "neutral",
  size = "sm",
  dot = false,
  children,
  ...props
}: ChipProps) {
  // Normalize string to match variants
  const v = (variant || "").toLowerCase();

  let styles = "bg-[#F2F1EE] text-[#6B6A64] border-[#E3DACC]";
  let dotColor = "bg-[#8A887F]";

  if (v === "confirmed" || v === "passed" || v === "approved" || v === "low") {
    styles = "bg-[#EBF2EB] text-[#47704A] border-[#D2E3D3]";
    dotColor = "bg-[#5E8C61]";
  } else if (v === "flaky" || v === "medium") {
    styles = "bg-[#FBF4E6] text-[#A67319] border-[#F4E2BD]";
    dotColor = "bg-[#D4A02A]";
  } else if (
    v === "not_reproduced" ||
    v === "failed" ||
    v === "rejected" ||
    v === "critical" ||
    v === "high" ||
    v === "error"
  ) {
    styles = "bg-[#FAEBE9] text-[#B83E31] border-[#F2CAC5]";
    dotColor = "bg-[#C4473A]";
  } else if (v === "clay") {
    styles = "bg-[#F6EDE8] text-[#C15F3C] border-[#F0D5C9]";
    dotColor = "bg-[#D97757]";
  } else if (v === "running" || v === "verifying" || v === "exploring" || v === "planning" || v === "executing") {
    styles = "bg-[#F5F2EB] text-[#7A6D52] border-[#E5DFCE]";
    dotColor = "bg-[#D97757] animate-pulse";
  }

  const sizeStyles = {
    xs: "text-[11px] px-1.5 py-0.5 rounded-md",
    sm: "text-xs px-2.5 py-0.5 rounded-full",
    md: "text-sm px-3 py-1 rounded-full",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-medium border whitespace-nowrap select-none",
        styles,
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotColor)} />}
      <span>{children}</span>
    </span>
  );
}
