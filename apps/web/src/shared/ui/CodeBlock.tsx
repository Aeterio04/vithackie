"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { Copy, Check, Download } from "lucide-react";

interface CodeBlockProps {
  code: string;
  language?: string;
  filename?: string;
  className?: string;
}

export function CodeBlock({
  code,
  language = "typescript",
  filename,
  className,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const lines = code.split("\n");

  const copyToClipboard = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadFile = () => {
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || `repro.${language === "typescript" ? "ts" : "txt"}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-[#E3DACC] bg-[#1E1E1C] text-[#E5E3DC] font-mono text-xs overflow-hidden shadow-xs",
        className
      )}
    >
      {/* Code Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#2B2A27] border-b border-[#3D3B36] select-none">
        <div className="flex items-center gap-2">
          {filename && (
            <span className="text-[11px] font-semibold text-[#FAF9F5] font-mono">
              {filename}
            </span>
          )}
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[#1E1E1C] text-[#A8A59B] border border-[#3D3B36]">
            {language}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={downloadFile}
            title="Download script"
            className="flex items-center gap-1 text-[11px] text-[#A8A59B] hover:text-[#E5E3DC] px-2 py-1 rounded hover:bg-[#3D3B36] transition-colors cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download</span>
          </button>

          <button
            onClick={copyToClipboard}
            title="Copy code"
            className="flex items-center gap-1 text-[11px] text-[#A8A59B] hover:text-[#E5E3DC] px-2 py-1 rounded hover:bg-[#3D3B36] transition-colors cursor-pointer"
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

      {/* Code Content with Line Numbers (Safe plain text rendering) */}
      <div className="p-3 overflow-x-auto max-h-[500px]">
        <table className="border-collapse w-full">
          <tbody>
            {lines.map((line, idx) => (
              <tr key={idx} className="hover:bg-[#2B2A27]/40 leading-relaxed">
                <td className="w-8 select-none text-[#6B6A64] text-right pr-4 align-top text-[11px]">
                  {idx + 1}
                </td>
                <td className="whitespace-pre text-[#E5E3DC] font-mono">
                  {line || " "}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
