import { apiClient } from "@/shared/lib/api/client";

export interface ProjectItem {
  id: string;
  name: string;
  slug: string;
  targetUrl: string;
  description?: string | null;
  defaultMode: string;
  budgets: {
    maxPages?: number;
    exploreSeconds?: number;
    maxTests?: number;
    testTimeoutMs?: number;
  };
  createdAt: string;
  updatedAt: string;
}

export interface CreateProjectPayload {
  name: string;
  slug?: string;
  targetUrl: string;
  description?: string;
  defaultMode?: "manual" | "autonomous";
  budgets?: {
    maxPages?: number;
    exploreSeconds?: number;
    maxTests?: number;
    testTimeoutMs?: number;
  };
}

export const projectsApi = {
  list: async (): Promise<ProjectItem[]> => {
    return apiClient.get<ProjectItem[]>("/api/v1/projects");
  },

  get: async (id: string): Promise<ProjectItem> => {
    return apiClient.get<ProjectItem>(`/api/v1/projects/${id}`);
  },

  create: async (payload: CreateProjectPayload): Promise<ProjectItem> => {
    return apiClient.post<ProjectItem>("/api/v1/projects", payload);
  },

  delete: async (id: string): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/projects/${id}`);
  },

  update: async (id: string, payload: Partial<CreateProjectPayload>): Promise<ProjectItem> => {
    return apiClient.put<ProjectItem>(`/api/v1/projects/${id}`, payload);
  },
};

