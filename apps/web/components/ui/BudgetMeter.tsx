import React from "react";
import { cn } from "@/lib/utils";

interface BudgetMeterProps {
  label: string;
  current: number;
  max: number;
  unit?: string;
  className?: string;
  size?: "sm" | "md";
}

export function BudgetMeter({
  label,
  current,
  max,
  unit = "",
  className,
  size = "md",
}: BudgetMeterProps) {
  const percentage = max > 0 ? Math.min(100, Math.round((current / max) * 100)) : 0;
  const isExhausted = current >= max;
  const isAmber = !isExhausted && percentage >= 80;

  let barColor = "bg-[#D97757]";
  let textColor = "text-[#6B6A64]";

  if (isExhausted) {
    barColor = "bg-[#C4473A]";
    textColor = "text-[#C4473A] font-semibold";
  } else if (isAmber) {
    barColor = "bg-[#D4A02A]";
    textColor = "text-[#A67319] font-medium";
  }

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-[#6B6A64] font-medium">{label}</span>
        <span className={cn("font-mono", textColor)}>
          {current}
          {unit} / {max}
          {unit} ({percentage}%)
          {isExhausted && <span className="ml-1 text-[11px]">(Exhausted)</span>}
        </span>
      </div>

      <div
        className={cn(
          "w-full bg-[#E3DACC]/60 rounded-full overflow-hidden",
          size === "sm" ? "h-1.5" : "h-2"
        )}
      >
        <div
          className={cn("h-full transition-all duration-300 rounded-full", barColor)}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
