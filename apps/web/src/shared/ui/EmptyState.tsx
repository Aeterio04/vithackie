import React from "react";
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-8 rounded-xl border border-dashed border-[#E3DACC] bg-[#FAF9F5]/60",
        className
      )}
    >
      {Icon && (
        <div className="w-12 h-12 rounded-full bg-[#F0EEE6] flex items-center justify-center text-[#8A887F] mb-3">
          <Icon className="w-6 h-6 stroke-[1.5]" />
        </div>
      )}
      <h4 className="font-heading text-lg text-[#141413] mb-1 font-normal">
        {title}
      </h4>
      {description && (
        <p className="text-sm text-[#6B6A64] max-w-sm mb-4 leading-relaxed">
          {description}
        </p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
