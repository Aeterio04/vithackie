import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { z } from "zod";
import { apiClient, uploadWithProgress, ApiError } from "./client";
import { API_ENDPOINTS } from "./config";
import {
  RunSchema,
  type Run,
  ConfigDefaultsSchema,
  type ConfigDefaults,
  TargetCheckResultSchema,
  type TargetCheckResult,
  HealthStatusSchema,
  type HealthStatus,
  AuthUserSchema,
  type AuthUser,
  CatalogTestSchema,
  type CatalogTest,
  ReviewDecisionSchema,
  type ReviewDecision,
  WorkerSchema,
  ExecutionTestSchema,
  type ExecutionTest,
  BugSchema,
  type Bug,
  ReportSchema,
  type Report,
  AppMapResponseSchema,
  type AppMapResponse,
  BudgetUsageSchema,
  ReviewMode,
  Budgets,
} from "@/types";

// ==========================================
// AUTH HOOKS
// ==========================================

export function useAuthMe(options?: Partial<UseQueryOptions<AuthUser, ApiError>>) {
  return useQuery<AuthUser, ApiError>({
    queryKey: ["auth", "me"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.AUTH_ME, {
        schema: AuthUserSchema,
      }),
    retry: false,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<
    AuthUser,
    ApiError,
    { username_or_email: string; password: string }
  >({
    mutationFn: (credentials) =>
      apiClient(API_ENDPOINTS.AUTH_LOGIN, {
        method: "POST",
        body: credentials,
        schema: AuthUserSchema,
      }),
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () =>
      apiClient(API_ENDPOINTS.AUTH_LOGOUT, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.clear();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    },
  });
}

// ==========================================
// SYSTEM & HEALTH HOOKS
// ==========================================

export function useHealth() {
  return useQuery<HealthStatus, ApiError>({
    queryKey: ["system", "health"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.HEALTH, {
        schema: HealthStatusSchema,
      }),
    refetchInterval: 30000, // Poll every 30s as specified
    staleTime: 15000,
  });
}

export function useConfigDefaults() {
  return useQuery<ConfigDefaults, ApiError>({
    queryKey: ["system", "configDefaults"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.CONFIG_DEFAULTS, {
        schema: ConfigDefaultsSchema,
      }),
    staleTime: 10 * 60 * 1000,
  });
}

export const StatsSchema = z.object({
  total_runs: z.number().default(0),
  confirmed_bugs: z.number().default(0),
  flaky_bugs: z.number().default(0),
  pending_reviews: z.number().default(0),
});
export type Stats = z.infer<typeof StatsSchema>;

export function useStats() {
  return useQuery<Stats, ApiError>({
    queryKey: ["stats"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.STATS, {
        schema: StatsSchema,
      }),
    staleTime: 30000,
  });
}

// ==========================================
// TARGET CHECK & SPECS
// ==========================================

export function useTargetCheck() {
  return useMutation<TargetCheckResult, ApiError, { target_url: string }>({
    mutationFn: ({ target_url }) =>
      apiClient(API_ENDPOINTS.TARGETS_CHECK, {
        method: "POST",
        body: { target_url },
        schema: TargetCheckResultSchema,
      }),
  });
}

export interface SpecUploadResult {
  spec_id: string;
  filename: string;
  file_size_bytes: number;
  item_count: number;
}

export const SpecUploadResultSchema = z.object({
  spec_id: z.string(),
  filename: z.string(),
  file_size_bytes: z.number().default(0),
  item_count: z.number().default(0),
});

export function useUploadSpec() {
  return useMutation<
    SpecUploadResult,
    ApiError,
    {
      file?: File;
      spec_text?: string;
      onProgress?: (percent: number) => void;
    }
  >({
    mutationFn: ({ file, spec_text, onProgress }) => {
      const formData = new FormData();
      if (file) {
        formData.append("file", file);
      } else if (spec_text) {
        formData.append("spec_text", spec_text);
      }
      return uploadWithProgress<SpecUploadResult>({
        endpoint: API_ENDPOINTS.SPECS_UPLOAD,
        formData,
        schema: SpecUploadResultSchema,
        onProgress: (percent) => onProgress?.(percent),
      });
    },
  });
}

// ==========================================
// RUNS HOOKS
// ==========================================

export function useRuns() {
  return useQuery<Run[], ApiError>({
    queryKey: ["runs"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUNS, {
        schema: z.array(RunSchema),
      }),
    staleTime: 10000,
  });
}

export function useRun(runId: string | null | undefined) {
  return useQuery<Run, ApiError>({
    queryKey: ["runs", runId],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_BY_ID(runId!), {
        schema: RunSchema,
      }),
    enabled: Boolean(runId),
    staleTime: 1000,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (
        status === "completed" ||
        status === "failed" ||
        status === "cancelled" ||
        status === "budget_exhausted"
      ) {
        return false;
      }
      return 2000;
    },
  });
}

export interface CreateRunPayload {
  project_id?: string;
  projectId?: string;
  target_url: string;
  prompt: string;
  spec_id?: string;
  spec_text?: string;
  review_mode: ReviewMode;
  budgets: Budgets;
  credentials?: {
    username?: string;
    password?: string;
  };
}

export function useProjects() {
  return useQuery<any[], ApiError>({
    queryKey: ["projects"],
    queryFn: () => apiClient("/api/v1/projects"),
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation<Run, ApiError, CreateRunPayload>({
    mutationFn: (payload) =>
      apiClient(API_ENDPOINTS.RUNS, {
        method: "POST",
        body: payload,
        schema: RunSchema,
      }),
    onSuccess: (newRun) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.setQueryData(["runs", newRun.id], newRun);
    },
  });
}

export function useStartRun() {
  const queryClient = useQueryClient();
  return useMutation<Run, ApiError, string>({
    mutationFn: (runId) =>
      apiClient(API_ENDPOINTS.RUN_START(runId), {
        method: "POST",
        schema: RunSchema,
      }),
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(["runs", updatedRun.id], updatedRun);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useCancelRun() {
  const queryClient = useQueryClient();
  return useMutation<Run, ApiError, string>({
    mutationFn: (runId) =>
      apiClient(API_ENDPOINTS.RUN_CANCEL(runId), {
        method: "POST",
        schema: RunSchema,
      }),
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(["runs", updatedRun.id], updatedRun);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useRetryRun() {
  const queryClient = useQueryClient();
  return useMutation<Run, ApiError, string>({
    mutationFn: (runId) =>
      apiClient(API_ENDPOINTS.RUN_RETRY(runId), {
        method: "POST",
        schema: RunSchema,
      }),
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(["runs", updatedRun.id], updatedRun);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

// ==========================================
// APP MAP HOOKS
// ==========================================

export function useAppMap(runId: string | null | undefined) {
  return useQuery<AppMapResponse, ApiError>({
    queryKey: ["runs", runId, "appMap"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_APP_MAP(runId!), {
        schema: AppMapResponseSchema,
      }),
    enabled: Boolean(runId),
  });
}

// ==========================================
// CATALOG & REVIEW HOOKS
// ==========================================

export function useCatalog(runId: string | null | undefined) {
  return useQuery<CatalogTest[], ApiError>({
    queryKey: ["runs", runId, "catalog"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_CATALOG(runId!), {
        schema: z.array(CatalogTestSchema),
      }),
    enabled: Boolean(runId),
  });
}

export function useUpdateCatalogTest(runId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    CatalogTest,
    ApiError,
    { testId: string; updates: Partial<CatalogTest> }
  >({
    mutationFn: ({ testId, updates }) =>
      apiClient(API_ENDPOINTS.RUN_CATALOG_TEST(runId, testId), {
        method: "PATCH",
        body: updates,
        schema: CatalogTestSchema,
      }),
    onSuccess: (updatedTest) => {
      queryClient.setQueryData<CatalogTest[]>(
        ["runs", runId, "catalog"],
        (old) =>
          old ? old.map((t) => (t.id === updatedTest.id ? updatedTest : t)) : []
      );
    },
  });
}

export interface ReviewDecisionSubmission {
  test_ids: string[];
  decision: "approved" | "rejected";
  reason?: string;
  priority_tier?: "P0" | "P0+P1" | "all" | "smoke";
}

export function useSubmitReview(runId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    { applied_count: number; run_status?: string },
    ApiError,
    ReviewDecisionSubmission,
    { previousCatalog?: CatalogTest[] }
  >({
    mutationFn: (payload) =>
      apiClient(API_ENDPOINTS.RUN_REVIEW(runId), {
        method: "POST",
        body: payload,
      }),
    // Optimistic update
    onMutate: async (submission) => {
      await queryClient.cancelQueries({
        queryKey: ["runs", runId, "catalog"],
      });
      const previousCatalog = queryClient.getQueryData<CatalogTest[]>([
        "runs",
        runId,
        "catalog",
      ]);

      if (previousCatalog) {
        queryClient.setQueryData<CatalogTest[]>(
          ["runs", runId, "catalog"],
          previousCatalog.map((test) => {
            if (submission.test_ids.includes(test.id)) {
              return {
                ...test,
                review_status: submission.decision,
                last_decision: {
                  test_id: test.id,
                  decision: submission.decision,
                  actor: "human",
                  reason: submission.reason || "",
                  at: new Date().toISOString(),
                },
              };
            }
            return test;
          })
        );
      }
      return { previousCatalog };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousCatalog) {
        queryClient.setQueryData(
          ["runs", runId, "catalog"],
          context.previousCatalog
        );
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["runs", runId, "catalog"],
      });
      queryClient.invalidateQueries({
        queryKey: ["runs", runId, "reviewLog"],
      });
      queryClient.invalidateQueries({ queryKey: ["runs", runId] });
    },
  });
}

export function useReviewLog(runId: string | null | undefined) {
  return useQuery<ReviewDecision[], ApiError>({
    queryKey: ["runs", runId, "reviewLog"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_REVIEW_LOG(runId!), {
        schema: z.array(ReviewDecisionSchema),
      }),
    enabled: Boolean(runId),
  });
}

// ==========================================
// EXECUTION & WORKERS HOOKS
// ==========================================

export const ExecutionStateSchema = z.object({
  workers: z.array(WorkerSchema).default([]),
  tests: z.array(ExecutionTestSchema).default([]),
  budget_usage: BudgetUsageSchema.optional(),
});
export type ExecutionState = z.infer<typeof ExecutionStateSchema>;

export function useExecution(runId: string | null | undefined) {
  return useQuery<ExecutionState, ApiError>({
    queryKey: ["runs", runId, "execution"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_EXECUTION(runId!), {
        schema: ExecutionStateSchema,
      }),
    enabled: Boolean(runId),
    refetchInterval: 2000,
  });
}

export function useTests(runId: string | null | undefined) {
  return useQuery<ExecutionTest[], ApiError>({
    queryKey: ["runs", runId, "tests"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_TESTS(runId!), {
        schema: z.array(ExecutionTestSchema),
      }),
    enabled: Boolean(runId),
    refetchInterval: 2000,
  });
}

// ==========================================
// BUGS HOOKS
// ==========================================

export function useBugs(runId: string | null | undefined) {
  return useQuery<Bug[], ApiError>({
    queryKey: ["runs", runId, "bugs"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_BUGS(runId!), {
        schema: z.array(BugSchema),
      }),
    enabled: Boolean(runId),
  });
}

export function useBug(bugId: string | null | undefined) {
  return useQuery<Bug, ApiError>({
    queryKey: ["bugs", bugId],
    queryFn: () =>
      apiClient(API_ENDPOINTS.BUG_BY_ID(bugId!), {
        schema: BugSchema,
      }),
    enabled: Boolean(bugId),
  });
}

// ==========================================
// REPORTS HOOKS
// ==========================================

export function useReport(runId: string | null | undefined) {
  return useQuery<Report, ApiError>({
    queryKey: ["runs", runId, "report"],
    queryFn: () =>
      apiClient(API_ENDPOINTS.RUN_REPORT(runId!), {
        schema: ReportSchema,
      }),
    enabled: Boolean(runId),
  });
}
