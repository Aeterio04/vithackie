"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "info";

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastContextType {
  toast: (item: Omit<ToastItem, "id">) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string, onRetry?: () => void) => void;
  info: (title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (item: Omit<ToastItem, "id">) => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;
      const newToast: ToastItem = { ...item, id };
      setToasts((prev) => [...prev, newToast]);

      // Auto dismiss after 5 seconds
      setTimeout(() => {
        removeToast(id);
      }, 5000);
    },
    [removeToast]
  );

  const success = useCallback(
    (title: string, message?: string) => {
      addToast({ type: "success", title, message });
    },
    [addToast]
  );

  const error = useCallback(
    (title: string, message?: string, onRetry?: () => void) => {
      addToast({
        type: "error",
        title,
        message,
        action: onRetry ? { label: "Retry", onClick: onRetry } : undefined,
      });
    },
    [addToast]
  );

  const info = useCallback(
    (title: string, message?: string) => {
      addToast({ type: "info", title, message });
    },
    [addToast]
  );

  useEffect(() => {
    const handleApiError = (e: Event) => {
      const customEvent = e as CustomEvent<{
        status: number;
        url: string;
        code: string;
        requestId?: string;
        message: string;
      }>;
      const detail = customEvent.detail;
      if (!detail) return;
      error(
        `HTTP ${detail.status}: ${detail.code}`,
        `${detail.message} • ${detail.url}${detail.requestId ? ` (Req ID: ${detail.requestId})` : ""}`
      );
    };

    window.addEventListener("kawach:api-error", handleApiError);
    return () => window.removeEventListener("kawach:api-error", handleApiError);
  }, [error]);

  return (
    <ToastContext.Provider value={{ toast: addToast, success, error, info }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => {
          let icon = <Info className="w-5 h-5 text-[#6B6A64]" />;
          let borderStyle = "border-[#E3DACC]";
          let bgStyle = "bg-white";

          if (t.type === "success") {
            icon = <CheckCircle2 className="w-5 h-5 text-[#5E8C61]" />;
            borderStyle = "border-[#D2E3D3]";
            bgStyle = "bg-[#FAFDF9]";
          } else if (t.type === "error") {
            icon = <AlertCircle className="w-5 h-5 text-[#C4473A]" />;
            borderStyle = "border-[#F2CAC5]";
            bgStyle = "bg-[#FFF9F9]";
          }

          return (
            <div
              key={t.id}
              className={cn(
                "pointer-events-auto p-4 rounded-xl border shadow-lg flex items-start gap-3 transition-all transform translate-y-0",
                bgStyle,
                borderStyle
              )}
            >
              <div className="shrink-0 mt-0.5">{icon}</div>

              <div className="flex-1 min-w-0">
                <h5 className="text-sm font-semibold text-[#141413]">
                  {t.title}
                </h5>
                {t.message && (
                  <p className="text-xs text-[#6B6A64] mt-0.5 leading-relaxed">
                    {t.message}
                  </p>
                )}
                {t.action && (
                  <button
                    onClick={() => {
                      t.action?.onClick();
                      removeToast(t.id);
                    }}
                    className="mt-2 text-xs font-semibold text-[#D97757] hover:underline cursor-pointer"
                  >
                    {t.action.label}
                  </button>
                )}
              </div>

              <button
                onClick={() => removeToast(t.id)}
                className="text-[#8A887F] hover:text-[#141413] p-1 rounded transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
