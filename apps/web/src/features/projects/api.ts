import { apiClient } from "@/shared/lib/api/client";

export interface ProjectItem {
  id: string;
  ownerId?: string;
  userId?: string;
  workspaceId?: string | null;
  name: string;
  slug: string;
  targetUrl: string;
  testUrl?: string;
  githubUrl?: string;
  patMasked?: string;
  hasPat?: boolean;
  description?: string | null;
  defaultMode: string;
  budgets?: {
    maxPages?: number;
    exploreSeconds?: number;
    maxTests?: number;
    testTimeoutMs?: number;
  };
  lastRunStatus?: string | null;
  savedTestCount?: number;
  createdAt: string;
  updatedAt?: string;
}

export interface CreateProjectPayload {
  name: string;
  slug?: string;
  targetUrl?: string;
  testUrl?: string;
  githubUrl?: string;
  pat?: string;
  workspaceId?: string;
  description?: string;
  defaultMode?: "manual" | "autonomous";
  budgets?: {
    maxPages?: number;
    exploreSeconds?: number;
    maxTests?: number;
    testTimeoutMs?: number;
  };
}

export interface UpdateProjectPayload {
  name?: string;
  targetUrl?: string;
  testUrl?: string;
  githubUrl?: string;
  pat?: string;
  description?: string;
  defaultMode?: "manual" | "autonomous";
  budgets?: {
    maxPages?: number;
    exploreSeconds?: number;
    maxTests?: number;
    testTimeoutMs?: number;
  };
}

export interface SavedTestItem {
  id: string;
  project_id: string;
  origin_run_id?: string | null;
  origin_test_case_id?: string | null;
  name: string;
  description?: string | null;
  script_path: string;
  tags: string[];
  is_active: boolean;
  last_result?: string | null;
  lastResult?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface GithubCommitItem {
  sha: string;
  fullSha?: string;
  message: string;
  author: string;
  date?: string;
  url?: string;
}

export interface GithubCommitsResponse {
  configured: boolean;
  message?: string;
  error?: string;
  owner?: string;
  repo?: string;
  commits: GithubCommitItem[];
}

export const projectsApi = {
  list: async (): Promise<ProjectItem[]> => {
    return apiClient<ProjectItem[]>("/api/v1/projects");
  },

  get: async (id: string): Promise<ProjectItem> => {
    return apiClient<ProjectItem>(`/api/v1/projects/${id}`);
  },

  create: async (payload: CreateProjectPayload): Promise<ProjectItem> => {
    return apiClient<ProjectItem>("/api/v1/projects", {
      method: "POST",
      body: payload,
    });
  },

  update: async (id: string, payload: UpdateProjectPayload): Promise<ProjectItem> => {
    return apiClient<ProjectItem>(`/api/v1/projects/${id}`, {
      method: "PUT",
      body: payload,
    });
  },

  delete: async (id: string): Promise<void> => {
    return apiClient<void>(`/api/v1/projects/${id}`, {
      method: "DELETE",
    });
  },

  getSavedTests: async (projectId: string): Promise<SavedTestItem[]> => {
    return apiClient<SavedTestItem[]>(`/api/v1/projects/${projectId}/saved-tests`);
  },

  runSavedTest: async (projectId: string, testId: string): Promise<{ runId: string; status: string }> => {
    return apiClient<{ runId: string; status: string }>(`/api/v1/projects/${projectId}/saved-tests/${testId}/run`, {
      method: "POST",
    });
  },

  runAllSavedTests: async (projectId: string): Promise<{ runId: string; status: string; totalTests: number }> => {
    return apiClient<{ runId: string; status: string; totalTests: number }>(`/api/v1/projects/${projectId}/saved-tests/run-all`, {
      method: "POST",
    });
  },

  getProjectRuns: async (projectId: string): Promise<any[]> => {
    return apiClient<any[]>(`/api/v1/projects/${projectId}/runs`);
  },

  getGithubCommits: async (projectId: string): Promise<GithubCommitsResponse> => {
    return apiClient<GithubCommitsResponse>(`/api/v1/projects/${projectId}/commits/github`);
  },
};
