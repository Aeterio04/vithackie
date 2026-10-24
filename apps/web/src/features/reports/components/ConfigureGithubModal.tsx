"use client";

import React, { useState } from "react";
import { fixesApi } from "@/features/fixes/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { KeyRound, Eye, EyeOff, Sparkles, Loader2, AlertCircle, ShieldAlert, GitBranch } from "lucide-react";

function GithubIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

interface ConfigureGithubModalProps {
  isOpen: boolean;
  onClose: () => void;
  runId: string;
  bugId?: string;
  defaultRepo?: string;
  onLaunchSuccess: (fixId: string) => void;
}

export function ConfigureGithubModal({
  isOpen,
  onClose,
  runId,
  bugId,
  defaultRepo = "",
  onLaunchSuccess,
}: ConfigureGithubModalProps) {
  const [repo, setRepo] = useState(defaultRepo);
  const [pat, setPat] = useState("");
  const [showPat, setShowPat] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanRepo = repo.trim();
    const cleanPat = pat.trim();

    if (!cleanRepo) {
      setError("Please specify the GitHub repository (e.g. owner/repo).");
      return;
    }
    if (!cleanPat) {
      setError("GitHub Personal Access Token (PAT) is required to open autonomous Pull Requests.");
      return;
    }

    setLoading(true);
    try {
      // 1. Save config to project
      await fixesApi.saveConfig(runId, cleanRepo, cleanPat);

      // 2. Launch fix pipeline
      const launchRes = await fixesApi.createFix({
        runId,
        bugId,
        repo: cleanRepo,
        githubPat: cleanPat,
      });

      onClose();
      onLaunchSuccess(launchRes.fixId);
    } catch (err: any) {
      setError(err.message || "Failed to save GitHub credentials or launch fix pipeline.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md bg-white border border-[#E3DACC] shadow-xl rounded-2xl p-6 sm:p-7">
        <DialogHeader className="space-y-2 pb-2">
          <div className="w-10 h-10 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center text-[#141413]">
            <GithubIcon className="w-5 h-5 text-[#D97757]" />
          </div>
          <DialogTitle className="text-xl font-heading font-medium text-[#141413] flex items-center gap-2">
            <span>Configure GitHub Auto-Fix</span>
            <span className="px-2 py-0.5 text-[10px] uppercase font-mono tracking-wider bg-[#EBF2EB] text-[#47704A] border border-[#D2E3D3] rounded-md font-semibold">
              Live PR
            </span>
          </DialogTitle>
          <p className="text-xs text-[#6B6A64] leading-relaxed">
            Kawach will verify the defect, fetch the latest commit on <code className="px-1 py-0.5 rounded bg-[#FAF9F5] text-[#141413] font-mono">origin/main</code>, synthesize the repair using LLM, and open an autonomous Pull Request.
          </p>
        </DialogHeader>

        {error && (
          <div className="p-3 rounded-xl bg-[#FAEBE9] border border-[#F2CAC5] text-[#C4473A] text-xs flex items-start gap-2.5 my-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="leading-snug">{error}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          {/* Repo Input */}
          <div className="space-y-1.5">
            <label htmlFor="github_repo" className="text-xs font-semibold text-[#141413] flex items-center gap-1.5">
              <GithubIcon className="w-3.5 h-3.5 text-[#8A887F]" />
              <span>Target Repository</span>
            </label>
            <input
              id="github_repo"
              type="text"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="e.g. owner/repo or https://github.com/..."
              className="w-full px-3 py-2 text-xs rounded-xl border border-[#E3DACC] bg-[#FAF9F5] text-[#141413] focus:outline-none focus:ring-2 focus:ring-[#D97757]/30 focus:border-[#D97757] transition-all font-mono"
              required
            />
          </div>

          {/* PAT Token Input */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="github_pat" className="text-xs font-semibold text-[#141413] flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-[#8A887F]" />
                <span>GitHub Personal Access Token (PAT)</span>
              </label>
              <a
                href="https://github.com/settings/tokens?type=beta"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-[#D97757] hover:underline"
              >
                Create token ↗
              </a>
            </div>

            <div className="relative">
              <input
                id="github_pat"
                type={showPat ? "text" : "password"}
                value={pat}
                onChange={(e) => setPat(e.target.value)}
                placeholder="github_pat_... or ghp_..."
                className="w-full px-3 py-2 pr-10 text-xs rounded-xl border border-[#E3DACC] bg-[#FAF9F5] text-[#141413] focus:outline-none focus:ring-2 focus:ring-[#D97757]/30 focus:border-[#D97757] transition-all font-mono"
                required
              />
              <button
                type="button"
                onClick={() => setShowPat(!showPat)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8A887F] hover:text-[#141413] p-1"
                aria-label={showPat ? "Hide token" : "Show token"}
              >
                {showPat ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
            <p className="text-[11px] text-[#8A887F] leading-tight">
              Requires <strong>Contents</strong> (Read/Write) and <strong>Pull requests</strong> (Read/Write) on the target repository.
            </p>
          </div>

          {/* Notice */}
          <div className="p-2.5 rounded-xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center gap-2 text-[11px] text-[#6B6A64]">
            <ShieldAlert className="w-3.5 h-3.5 text-[#8A887F] shrink-0" />
            <span>Tokens are symmetrically encrypted with Fernet and never logged.</span>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={loading}
              className="gap-2 bg-[#D97757] hover:bg-[#C26243] text-white"
            >
              {loading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Launching Pipeline...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Save & Launch Auto-Fix</span>
                </>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
