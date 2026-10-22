import React from "react";
import { cn } from "@/lib/utils";
import { type RunStatus, mapStatusToStep } from "@/types";
import { Check, AlertCircle, XCircle } from "lucide-react";

interface StepperProps {
  status: RunStatus;
  className?: string;
}

const STEPS = [
  { key: "explore", label: "Explore" },
  { key: "plan", label: "Plan" },
  { key: "review", label: "Review" },
  { key: "execute", label: "Execute" },
  { key: "verify", label: "Verify" },
  { key: "report", label: "Report" },
] as const;

export function Stepper({ status, className }: StepperProps) {
  const { stepIndex, isTerminal } = mapStatusToStep(status);
  const isFailed = status === "failed" || status === "cancelled";
  const isBudgetExhausted = status === "budget_exhausted";

  return (
    <div className={cn("w-full py-2", className)}>
      <div className="flex items-center justify-between relative">
        {/* Connecting track line */}
        <div className="absolute top-4 left-6 right-6 h-0.5 bg-[#E3DACC] -z-0" />
        
        {/* Active progress track */}
        <div
          className="absolute top-4 left-6 h-0.5 bg-[#D97757] transition-all duration-500 -z-0"
          style={{
            width: `${Math.min(100, Math.max(0, (stepIndex / (STEPS.length - 1)) * 100))}%`,
          }}
        />

        {STEPS.map((s, idx) => {
          const isPassed = idx < stepIndex || (idx === stepIndex && isTerminal && !isFailed);
          const isCurrent = idx === stepIndex && !isTerminal;
          const isCurrentError = idx === stepIndex && isFailed;

          return (
            <div
              key={s.key}
              className="flex flex-col items-center group relative z-10"
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold transition-all shadow-xs border-2",
                  isPassed
                    ? "bg-[#D97757] text-white border-[#D97757]"
                    : isCurrentError
                    ? "bg-[#FAEBE9] text-[#C4473A] border-[#C4473A]"
                    : isCurrent
                    ? "bg-white text-[#D97757] border-[#D97757] ring-4 ring-[#D97757]/15"
                    : "bg-[#F0EEE6] text-[#8A887F] border-[#E3DACC]"
                )}
              >
                {isPassed ? (
                  <Check className="w-4 h-4 stroke-[2.5]" />
                ) : isCurrentError ? (
                  <XCircle className="w-4 h-4" />
                ) : isCurrent && isBudgetExhausted ? (
                  <AlertCircle className="w-4 h-4 text-[#D4A02A]" />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              <span
                className={cn(
                  "mt-2 text-xs font-medium tracking-tight whitespace-nowrap transition-colors",
                  isCurrent
                    ? "text-[#141413] font-semibold"
                    : isPassed
                    ? "text-[#6B6A64]"
                    : "text-[#8A887F]"
                )}
              >
                {s.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
