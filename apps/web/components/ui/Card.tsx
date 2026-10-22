import React from "react";
import { cn } from "@/lib/utils";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "bordered";
}

export function Card({
  className,
  variant = "default",
  children,
  ...props
}: CardProps) {
  const variantStyles = {
    default: "bg-white border border-[#E3DACC] shadow-[0_1px_2px_rgba(20,20,19,0.05)]",
    subtle: "bg-[#F0EEE6]/50 border border-[#E3DACC]/80",
    bordered: "bg-transparent border border-[#E3DACC]",
  };

  return (
    <div
      className={cn("rounded-[16px] p-5 transition-shadow", variantStyles[variant], className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-center justify-between pb-3 border-b border-[#E3DACC]/60 mb-4", className)} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("font-heading text-lg font-normal text-[#141413] tracking-tight", className)} {...props}>
      {children}
    </h3>
  );
}
