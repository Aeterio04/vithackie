"use client";

import React, { useRef, useState, useCallback } from "react";
import { cn, formatBytes } from "@/lib/utils";
import { UploadCloud, FileText, X, AlertCircle } from "lucide-react";

interface FileDropzoneProps {
  acceptedExtensions?: string[];
  maxSizeMb?: number;
  selectedFile: File | null;
  onFileSelect: (file: File | null) => void;
  uploadProgress?: number | null; // 0-100
  disabled?: boolean;
  className?: string;
}

export function FileDropzone({
  acceptedExtensions = [".md", ".txt", ".pdf", ".json", ".yaml", ".yml"],
  maxSizeMb = 10,
  selectedFile,
  onFileSelect,
  uploadProgress = null,
  disabled = false,
  className,
}: FileDropzoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const validateFile = useCallback(
    (file: File): boolean => {
      setErrorMessage(null);
      const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
      if (acceptedExtensions.length > 0 && !acceptedExtensions.includes(ext)) {
        setErrorMessage(
          `Invalid file format (${ext}). Allowed: ${acceptedExtensions.join(", ")}`
        );
        return false;
      }
      const maxBytes = maxSizeMb * 1024 * 1024;
      if (file.size > maxBytes) {
        setErrorMessage(
          `File is too large (${formatBytes(file.size)}). Maximum allowed: ${maxSizeMb} MB`
        );
        return false;
      }
      return true;
    },
    [acceptedExtensions, maxSizeMb]
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (disabled) return;
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (disabled) return;
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (validateFile(file)) {
        onFileSelect(file);
      }
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (validateFile(file)) {
        onFileSelect(file);
      }
    }
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    onFileSelect(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className={cn("space-y-2", className)}>
      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedExtensions.join(",")}
        onChange={handleFileInputChange}
        className="hidden"
        disabled={disabled}
      />

      {!selectedFile ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !disabled && fileInputRef.current?.click()}
          className={cn(
            "border-2 border-dashed rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors",
            isDragOver
              ? "border-[#D97757] bg-[#F6EDE8]/50"
              : "border-[#E3DACC] bg-[#FAF9F5] hover:bg-[#F0EEE6]/50",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <div className="w-10 h-10 rounded-full bg-[#F0EEE6] flex items-center justify-center text-[#D97757] mb-2">
            <UploadCloud className="w-5 h-5 stroke-[1.5]" />
          </div>
          <p className="text-sm font-medium text-[#141413]">
            Drop your spec file here, or{" "}
            <span className="text-[#D97757] underline">browse</span>
          </p>
          <p className="text-xs text-[#8A887F] mt-1 font-mono">
            {acceptedExtensions.join(", ")} (up to {maxSizeMb} MB)
          </p>
        </div>
      ) : (
        <div className="border border-[#E3DACC] rounded-xl p-4 bg-white shadow-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-lg bg-[#F6EDE8] text-[#D97757] flex items-center justify-center shrink-0">
                <FileText className="w-5 h-5 stroke-[1.5]" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-[#141413] truncate">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-[#8A887F] font-mono">
                  {formatBytes(selectedFile.size)}
                </p>
              </div>
            </div>

            {!disabled && (
              <button
                type="button"
                onClick={handleRemove}
                className="text-[#8A887F] hover:text-[#C4473A] p-1.5 rounded-lg hover:bg-[#FAEBE9] transition-colors cursor-pointer"
                title="Remove file"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {uploadProgress !== null && uploadProgress !== undefined && (
            <div className="mt-3 space-y-1">
              <div className="flex justify-between text-[11px] font-mono text-[#6B6A64]">
                <span>Uploading...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full bg-[#F0EEE6] h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-[#D97757] h-full transition-all duration-200 rounded-full"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center gap-1.5 text-xs text-[#C4473A] mt-1">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
