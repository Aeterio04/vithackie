"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { type StreamLogEntry } from "@/hooks/useRunStream";
import { Copy, Check, ArrowDown, Trash2 } from "lucide-react";

interface LogViewerProps {
  logs: StreamLogEntry[];
  onClear?: () => void;
  className?: string;
  maxHeight?: string;
}

export function LogViewer({
  logs,
  onClear,
  className,
  maxHeight = "360px",
}: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAutoScroll, setIsAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const [levelFilter, setLevelFilter] = useState<string>("all");

  const filteredLogs = useMemo(() => {
    if (levelFilter === "all") return logs;
    return logs.filter((l) => l.level === levelFilter);
  }, [logs, levelFilter]);

  // Handle user manual scroll
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 30;
    setIsAutoScroll(isAtBottom);
  };

  // Scroll to bottom when new logs arrive if auto-scroll is on
  useEffect(() => {
    if (isAutoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredLogs, isAutoScroll]);

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
      setIsAutoScroll(true);
    }
  };

  const copyAllLogs = () => {
    const text = logs
      .map((l) => `[${l.timestamp}] [${l.level.toUpperCase()}] ${l.source ? `[${l.source}] ` : ""}${l.message}`)
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-[#E3DACC] bg-[#1E1E1C] text-[#E5E3DC] font-mono text-xs flex flex-col overflow-hidden shadow-xs",
        className
      )}
    >
      {/* Log Header Controls */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#2B2A27] border-b border-[#3D3B36] select-none">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold tracking-wider uppercase text-[#A8A59B]">
            Logs ({filteredLogs.length})
          </span>
          <div className="flex items-center gap-1 bg-[#1E1E1C] p-0.5 rounded-md border border-[#3D3B36]">
            {["all", "info", "warn", "error"].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setLevelFilter(lvl)}
                className={cn(
                  "px-2 py-0.5 text-[10px] uppercase font-mono rounded cursor-pointer transition-colors",
                  levelFilter === lvl
                    ? "bg-[#D97757] text-white"
                    : "text-[#A8A59B] hover:text-white"
                )}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onClear && (
            <button
              onClick={onClear}
              title="Clear logs"
              className="text-[#A8A59B] hover:text-[#E5E3DC] p-1 rounded hover:bg-[#3D3B36] transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}

          <button
            onClick={copyAllLogs}
            title="Copy all logs"
            className="flex items-center gap-1 text-[11px] text-[#A8A59B] hover:text-[#E5E3DC] px-2 py-1 rounded hover:bg-[#3D3B36] transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-[#5E8C61]" />
                <span className="text-[#5E8C61]">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Log Body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{ maxHeight }}
        className="overflow-y-auto p-3 space-y-1 relative"
      >
        {filteredLogs.length === 0 ? (
          <div className="text-[#6B6A64] py-8 text-center italic">
            Waiting for logs from agent pipeline...
          </div>
        ) : (
          filteredLogs.map((log) => {
            let levelColor = "text-[#A8A59B]";
            if (log.level === "error") levelColor = "text-[#E57373]";
            if (log.level === "warn") levelColor = "text-[#FFD54F]";
            if (log.level === "info") levelColor = "text-[#81C784]";

            return (
              <div key={log.id} className="leading-relaxed hover:bg-[#2B2A27]/50 px-1 py-0.5 rounded break-all">
                <span className="text-[#6B6A64] mr-2">
                  {log.timestamp.split("T")[1]?.replace("Z", "") || log.timestamp}
                </span>
                <span className={cn("font-bold mr-2 uppercase", levelColor)}>
                  [{log.level}]
                </span>
                {log.source && (
                  <span className="text-[#D97757] mr-2">[{log.source}]</span>
                )}
                {/* Always render untrusted log messages as plain text string */}
                <span className="text-[#E5E3DC]">{log.message}</span>
              </div>
            );
          })
        )}
      </div>

      {/* Paused auto-scroll pill */}
      {!isAutoScroll && (
        <div className="bg-[#2B2A27]/90 border-t border-[#3D3B36] px-3 py-1.5 flex items-center justify-between text-xs text-[#FFD54F]">
          <span>Auto-scroll paused (scrolled up)</span>
          <button
            onClick={scrollToBottom}
            className="flex items-center gap-1 text-[11px] font-semibold text-[#D97757] hover:underline cursor-pointer"
          >
            <ArrowDown className="w-3 h-3" />
            Resume auto-scroll
          </button>
        </div>
      )}
    </div>
  );
}
