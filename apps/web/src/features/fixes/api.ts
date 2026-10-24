import { apiClient } from "@/shared/lib/api/client";
import { API_ENDPOINTS } from "@/shared/lib/api/config";

export interface FixReadiness {
  configured: boolean;
  hasPat: boolean;
  githubUrl: string;
  repo: string;
  targetUrl: string;
  projectId?: string;
  projectName?: string;
}

export interface FixSession {
  fixId: string;
  runId: string;
  bugId?: string;
  bugTitle?: string;
  repo: string;
  targetUrl: string;
  dryRun: boolean;
  status:
    | "starting"
    | "verifying"
    | "collecting"
    | "analyzing"
    | "raising_pr"
    | "pr_opened"
    | "pr_exists"
    | "dry_run_ready"
    | "not_reproduced"
    | "flaky"
    | "no_editable_changes"
    | "fix_not_possible"
    | "github_error"
    | "failed";
  stage: "verifier" | "collector" | "llm" | "pr" | "completed";
  currentStep: string;
  progress: number;
  logs: Array<{
    timestamp: string;
    message: string;
    level: "info" | "success" | "warning" | "error";
  }>;
  verification?: {
    runs: Array<{
      index: number;
      passed: boolean;
      duration_ms: number;
      error_text?: string;
    }>;
    failures: number;
    verdict: "confirmed" | "flaky" | "not_reproduced";
    observed_error?: string;
  };
  commitContext?: {
    sha?: string;
    author?: string;
    message?: string;
    summary?: {
      sha: string;
      author: string;
      message: string;
      timestamp?: string;
    };
    files?: Array<{
      filename?: string;
      path?: string;
      status?: string;
      additions?: number;
      deletions?: number;
      patch?: string;
    }>;
  };
  proposal?: {
    can_fix: boolean;
    confidence: number;
    root_cause: string;
    explanation: string;
    edits: Array<{
      path: string;
      old_str: string;
      new_str: string;
    }>;
    pr_title: string;
    pr_summary: string;
  };
  pullRequest?: {
    number: number;
    url: string;
    branch: string;
    title: string;
    created_at?: string;
  };
  error?: string;
  playwrightScript?: string;
  createdAt: string;
  updatedAt: string;
}

export const fixesApi = {
  checkReadiness: async (runId: string): Promise<FixReadiness> => {
    return apiClient<FixReadiness>(API_ENDPOINTS.RUN_FIX_READINESS(runId));
  },

  saveConfig: async (
    runId: string,
    githubUrl: string,
    pat: string
  ): Promise<{ success: boolean; githubUrl: string; hasPat: boolean }> => {
    return apiClient(API_ENDPOINTS.RUN_FIX_CONFIG(runId), {
      method: "POST",
      body: { github_url: githubUrl, pat },
    });
  },

  createFix: async (payload: {
    runId: string;
    bugId?: string;
    repo?: string;
    githubPat?: string;
    targetUrl?: string;
    dryRun?: boolean;
  }): Promise<{ fixId: string; status: string; repo?: string }> => {
    return apiClient(API_ENDPOINTS.FIXES, {
      method: "POST",
      body: {
        run_id: payload.runId,
        bug_id: payload.bugId,
        repo: payload.repo,
        github_pat: payload.githubPat,
        target_url: payload.targetUrl,
        dry_run: payload.dryRun ?? false,
      },
    });
  },

  getFixStatus: async (fixId: string): Promise<FixSession> => {
    return apiClient<FixSession>(API_ENDPOINTS.FIX_BY_ID(fixId));
  },
};
