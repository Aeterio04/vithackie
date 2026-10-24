"use client";

import React, { useState, useEffect, useCallback } from "react";
import { projectsApi, GithubCommitItem, GithubCommitsResponse } from "@/features/projects/api";
import { Button } from "@/shared/ui/Button";
import { useToast } from "@/shared/ui/Toast";
import {
  GitCommit,
  GitBranch,
  ExternalLink,
  Loader2,
  AlertCircle,
  RefreshCw,
  Settings,
  Calendar,
  User,
  ShieldAlert,
} from "lucide-react";

interface CommitsTabProps {
  projectId: string;
  onGoToSettings?: () => void;
}

export function CommitsTab({ projectId, onGoToSettings }: CommitsTabProps) {
  const { toast } = useToast();
  const [data, setData] = useState<GithubCommitsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCommits = useCallback(async () => {
    setLoading(true);
    try {
      const res = await projectsApi.getGithubCommits(projectId);
      setData(res);
    } catch (err: any) {
      toast({
        type: "error",
        title: "GitHub Sync Failed",
        description: err?.message || "Could not retrieve GitHub commits.",
      });
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    fetchCommits();
  }, [fetchCommits]);

  if (loading) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
        <p className="text-xs text-text-secondary">Fetching repository commits...</p>
      </div>
    );
  }

  // Case 1: GitHub URL or PAT not configured
  if (!data?.configured) {
    return (
      <div className="bg-white border border-card-border rounded-2xl p-10 max-w-xl mx-auto text-center shadow-xs">
        <div className="w-14 h-14 rounded-2xl bg-cloud border border-card-border flex items-center justify-center mx-auto mb-4 text-clay">
          <GitBranch className="w-7 h-7" />
        </div>

        <h3 className="font-heading text-xl font-normal text-text-primary mb-2">
          GitHub Repository Not Configured
        </h3>

        <p className="text-xs text-text-secondary leading-relaxed mb-6">
          Connect your GitHub repository and Personal Access Token (PAT) in Project Settings to view recent commits, inspect changed code diffs, and run automated regression suites on every push.
        </p>

        <div className="bg-ivory border border-card-border rounded-xl p-4 text-left mb-6 space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-text-primary">
            <GitCommit className="w-4 h-4 text-clay" />
            <span>Integrated Git Capabilities:</span>
          </div>
          <ul className="text-xs text-text-secondary space-y-1 list-disc list-inside">
            <li>Read-only inspection of recent commit history</li>
            <li>Diff-aware test selection for changed components</li>
            <li>Zero automated push safety invariant</li>
          </ul>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={onGoToSettings}
          className="gap-2 mx-auto"
        >
          <Settings className="w-4 h-4" />
          <span>Configure GitHub in Settings</span>
        </Button>
      </div>
    );
  }

  // Case 2: Configured, but error returned (e.g. invalid PAT or 404 repo)
  if (data.error) {
    return (
      <div className="space-y-6">
        <div className="bg-status-failed-bg border border-status-failed/30 rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-status-failed shrink-0 mt-0.5" />
            <div>
              <h4 className="text-xs font-semibold text-text-primary">
                GitHub Synchronization Error
              </h4>
              <p className="text-xs text-status-failed mt-0.5">
                {data.error}
              </p>
              <p className="text-[11px] text-text-secondary mt-1">
                Please verify that your GitHub repository URL is correct and your Personal Access Token has repository read permissions.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchCommits}
              className="gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={onGoToSettings}
              className="gap-1.5"
            >
              <Settings className="w-3.5 h-3.5" />
              <span>Fix Settings</span>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Case 3: Successfully loaded commits
  const commits = data.commits || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-card-border rounded-2xl p-6 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-heading text-xl font-normal text-text-primary">
              Recent Commits
            </h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-cloud text-text-secondary border border-card-border">
              {commits.length} commits
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs text-text-secondary font-mono mt-1">
            <GitBranch className="w-3.5 h-3.5 text-clay" />
            <span>{data.owner}/{data.repo}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchCommits}
            className="gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={onGoToSettings}
            className="gap-1.5"
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Settings</span>
          </Button>
        </div>
      </div>

      {commits.length === 0 ? (
        <div className="bg-white border border-card-border rounded-2xl p-10 text-center text-xs text-text-secondary shadow-xs">
          No commits found in the default branch of this repository.
        </div>
      ) : (
        <div className="space-y-3">
          {commits.map((c: GithubCommitItem) => (
            <div
              key={c.sha}
              className="bg-white border border-card-border rounded-2xl p-4 sm:p-5 shadow-xs hover:border-card-border transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              <div className="space-y-1.5 max-w-2xl">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-cloud text-text-primary border border-card-border">
                    {c.sha.slice(0, 7)}
                  </span>
                  <p className="text-sm font-medium text-text-primary">
                    {c.message.split("\n")[0]}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-tertiary font-mono">
                  <div className="flex items-center gap-1">
                    <User className="w-3.5 h-3.5" />
                    <span>{c.author}</span>
                  </div>

                  {c.date && (
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" />
                      <span>{new Date(c.date).toLocaleString()}</span>
                    </div>
                  )}
                </div>
              </div>

              {c.url && (
                <div className="shrink-0">
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button variant="secondary" size="sm" className="gap-1.5">
                      <span>View on GitHub</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </Button>
                  </a>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
