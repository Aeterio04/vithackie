import { z } from "zod";

// --- Run Status & Mode ---
export const RunStatusSchema = z.enum([
  "created",
  "exploring",
  "planning",
  "awaiting_review",
  "executing",
  "verifying",
  "reporting",
  "completed",
  "failed",
  "cancelled",
  "budget_exhausted",
]);
export type RunStatus = z.infer<typeof RunStatusSchema>;

export const ReviewModeSchema = z.enum(["manual", "autonomous"]);
export type ReviewMode = z.infer<typeof ReviewModeSchema>;

export const StepperStepSchema = z.enum([
  "explore",
  "plan",
  "review",
  "execute",
  "verify",
  "report",
]);
export type StepperStep = z.infer<typeof StepperStepSchema>;

// Map RunStatus to 6-step Stepper
export function mapStatusToStep(status: RunStatus): {
  step: StepperStep;
  stepIndex: number;
  isTerminal: boolean;
} {
  switch (status) {
    case "created":
      return { step: "explore", stepIndex: 0, isTerminal: false };
    case "exploring":
      return { step: "explore", stepIndex: 0, isTerminal: false };
    case "planning":
      return { step: "plan", stepIndex: 1, isTerminal: false };
    case "awaiting_review":
      return { step: "review", stepIndex: 2, isTerminal: false };
    case "executing":
      return { step: "execute", stepIndex: 3, isTerminal: false };
    case "verifying":
      return { step: "verify", stepIndex: 4, isTerminal: false };
    case "reporting":
      return { step: "report", stepIndex: 5, isTerminal: false };
    case "completed":
    case "failed":
    case "cancelled":
    case "budget_exhausted":
      return { step: "report", stepIndex: 5, isTerminal: true };
    default:
      return { step: "explore", stepIndex: 0, isTerminal: false };
  }
}

// --- Budgets ---
export const BudgetsSchema = z.object({
  max_pages: z.number().default(20),
  max_steps_per_test: z.number().default(30),
  max_run_minutes: z.number().default(15),
  parallel_workers: z.number().min(1).max(4).default(2),
});
export type Budgets = z.infer<typeof BudgetsSchema>;

export const BudgetUsageSchema = z.object({
  pages_crawled: z.number().default(0),
  steps_executed: z.number().default(0),
  elapsed_minutes: z.number().default(0),
  active_workers: z.number().default(0),
});
export type BudgetUsage = z.infer<typeof BudgetUsageSchema>;

// --- Run Counts ---
export const RunCountsSchema = z.object({
  total_tests: z.number().default(0),
  passed_tests: z.number().default(0),
  failed_tests: z.number().default(0),
  suspected_bugs: z.number().default(0),
  confirmed_bugs: z.number().default(0),
  flaky_bugs: z.number().default(0),
  not_reproduced_bugs: z.number().default(0),
  pending_reviews: z.number().default(0),
});
export type RunCounts = z.infer<typeof RunCountsSchema>;

// --- Run Model ---
export const RunSchema = z.object({
  id: z.string(),
  target_url: z.string(),
  prompt: z.string().default(""),
  review_mode: ReviewModeSchema.default("manual"),
  status: RunStatusSchema,
  progress: z.number().min(0).max(100).default(0),
  created_at: z.string(),
  finished_at: z.string().nullable().optional(),
  budgets: BudgetsSchema.optional(),
  budget_usage: BudgetUsageSchema.optional(),
  counts: RunCountsSchema.optional(),
});
export type Run = z.infer<typeof RunSchema>;

// --- Review Decision ---
export const ReviewDecisionSchema = z.object({
  test_id: z.string(),
  decision: z.enum(["approved", "rejected", "edited"]),
  actor: z.enum(["human", "reviewer_agent"]),
  reason: z.string().default(""),
  at: z.string(),
});
export type ReviewDecision = z.infer<typeof ReviewDecisionSchema>;

// --- Catalog Test ---
export const TestPrioritySchema = z.enum(["low", "medium", "high", "critical"]);
export type TestPriority = z.infer<typeof TestPrioritySchema>;

export const TestReviewStatusSchema = z.enum(["pending", "approved", "rejected", "edited"]);
export type TestReviewStatus = z.infer<typeof TestReviewStatusSchema>;

export const CatalogTestSchema = z.object({
  id: z.string(),
  title: z.string(),
  spec_item_ids: z.array(z.string()).default([]),
  steps: z.array(z.string()).default([]),
  expected_result: z.string(),
  priority: TestPrioritySchema.default("medium"),
  review_status: TestReviewStatusSchema.default("pending"),
  last_decision: ReviewDecisionSchema.nullable().optional(),
});
export type CatalogTest = z.infer<typeof CatalogTestSchema>;

// --- Test Execution Status ---
export const TestStatusSchema = z.preprocess(
  (val) => {
    if (typeof val === "string") {
      const s = val.toLowerCase();
      if (s === "environment_error") return "error";
      if (
        s === "assertion_failure" ||
        s === "test_error" ||
        s === "script_error" ||
        s === "setup_error"
      )
        return "failed";
      if (s === "passed_with_issues") return "passed";
      if (s === "not_run") return "skipped";
      return s;
    }
    return val;
  },
  z.enum([
    "queued",
    "running",
    "passed",
    "failed",
    "skipped",
    "error", // Infrastructure failure, never counted as a bug
  ])
);
export type TestStatus = z.infer<typeof TestStatusSchema>;

export const ExecutionTestSchema = z.object({
  id: z.string(),
  run_id: z.string().optional(),
  catalog_test_id: z.string().optional(),
  title: z.string(),
  status: TestStatusSchema,
  duration_ms: z.number().nullable().optional(),
  worker_id: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
});
export type ExecutionTest = z.infer<typeof ExecutionTestSchema>;

// --- Bugs & Replays ---
export const BugSeveritySchema = z.enum(["low", "medium", "high", "critical"]);
export type BugSeverity = z.infer<typeof BugSeveritySchema>;

export const BugSourceSchema = z.enum(["test_runner", "exploratory"]);
export type BugSource = z.infer<typeof BugSourceSchema>;

export const BugStatusSchema = z.preprocess(
  (val) => (val === "candidate" ? "suspected" : val),
  z.enum([
    "suspected",
    "verifying",
    "confirmed",
    "flaky",
    "not_reproduced",
  ])
);
export type BugStatus = z.infer<typeof BugStatusSchema>;

export const ReplayResultSchema = z.enum([
  "reproduced",
  "not_reproduced",
  "error",
  "pending",
]);
export type ReplayResult = z.infer<typeof ReplayResultSchema>;

export const ReplaySchema = z.object({
  index: z.number().min(1).max(3),
  result: ReplayResultSchema,
  duration_ms: z.number().nullable().optional(),
  video_url: z.string().nullable().optional(),
  timestamp: z.string().nullable().optional(),
});
export type Replay = z.infer<typeof ReplaySchema>;

export const BugEvidenceSchema = z.object({
  screenshots: z.array(z.string()).default([]),
  video_url: z.string().nullable().optional(),
  trace_url: z.string().nullable().optional(),
  logs: z.string().nullable().optional(),
  console: z.array(z.string()).default([]),
  network: z.array(z.record(z.string(), z.unknown())).default([]),
});
export type BugEvidence = z.infer<typeof BugEvidenceSchema>;

export const BugSchema = z.object({
  id: z.string(),
  run_id: z.string().optional(),
  title: z.string(),
  severity: BugSeveritySchema,
  source: BugSourceSchema,
  spec_item_ids: z.array(z.string()).default([]),
  status: BugStatusSchema,
  replays: z.array(ReplaySchema).default([]),
  steps_to_reproduce: z.array(z.string()).default([]),
  expected: z.string().default(""),
  actual: z.string().default(""),
  evidence: BugEvidenceSchema.optional(),
  repro_script_url: z.string().nullable().optional(),
  created_at: z.string().optional(),
});
export type Bug = z.infer<typeof BugSchema>;

/**
 * Replay tally helper: checks if the status matches the 3 deterministic replays
 * 3/3 => Confirmed
 * 1-2/3 => Flaky
 * 0/3 (all 3 done, 0 reproduced) => Not reproduced
 */
export function verifyReplayStatus(bug: Bug): {
  reproducedCount: number;
  totalReplays: number;
  expectedStatus: BugStatus | null;
  hasMismatch: boolean;
} {
  const completedReplays = bug.replays.filter(
    (r) => r.result === "reproduced" || r.result === "not_reproduced"
  );
  const reproducedCount = bug.replays.filter(
    (r) => r.result === "reproduced"
  ).length;

  if (completedReplays.length < 3) {
    return {
      reproducedCount,
      totalReplays: completedReplays.length,
      expectedStatus: bug.status === "verifying" ? "verifying" : "suspected",
      hasMismatch:
        bug.status === "confirmed" ||
        bug.status === "flaky" ||
        bug.status === "not_reproduced",
    };
  }

  let expectedStatus: BugStatus;
  if (reproducedCount === 3) {
    expectedStatus = "confirmed";
  } else if (reproducedCount >= 1) {
    expectedStatus = "flaky";
  } else {
    expectedStatus = "not_reproduced";
  }

  const hasMismatch = bug.status !== expectedStatus;
  return {
    reproducedCount,
    totalReplays: 3,
    expectedStatus,
    hasMismatch,
  };
}

// --- Workers ---
export const WorkerKindSchema = z.enum(["runner", "exploratory"]);
export type WorkerKind = z.infer<typeof WorkerKindSchema>;

export const WorkerStatusSchema = z.enum([
  "idle",
  "running",
  "verifying",
  "offline",
  "error",
]);
export type WorkerStatus = z.infer<typeof WorkerStatusSchema>;

export const WorkerSchema = z.object({
  id: z.string(),
  kind: WorkerKindSchema,
  current_test_id: z.string().nullable().optional(),
  current_step: z.string().nullable().optional(),
  status: WorkerStatusSchema,
  latest_screenshot_url: z.string().nullable().optional(),
  screenshot_updated_at: z.string().nullable().optional(),
});
export type Worker = z.infer<typeof WorkerSchema>;

export const ExecutionStateSchema = z.object({
  workers: z.array(WorkerSchema).default([]),
  tests: z.array(ExecutionTestSchema).default([]),
  budget_usage: BudgetUsageSchema.optional(),
});
export type ExecutionState = z.infer<typeof ExecutionStateSchema>;

// --- App Map (Explorer) ---
export interface AppMapNode {
  id: string;
  url: string;
  title?: string;
  depth: number;
  status_code?: number;
  discovered_at?: string;
  children?: AppMapNode[];
  actions_found?: string[];
}

export const AppMapNodeSchema: z.ZodType<AppMapNode> = z.lazy(() =>
  z.object({
    id: z.string(),
    url: z.string(),
    title: z.string().optional(),
    depth: z.number().default(0),
    status_code: z.number().optional(),
    discovered_at: z.string().optional(),
    children: z.array(AppMapNodeSchema).optional(),
    actions_found: z.array(z.string()).optional(),
  })
);

export const AppMapResponseSchema = z.object({
  run_id: z.string(),
  total_pages: z.number().default(0),
  max_pages_budget: z.number().default(20),
  root_node: AppMapNodeSchema.nullable().optional(),
});
export type AppMapResponse = z.infer<typeof AppMapResponseSchema>;

// --- Reports ---
export const ReportSpecCoverageSchema = z.object({
  total_items: z.number().default(0),
  covered_items: z.number().default(0),
  covered_item_ids: z.array(z.string()).default([]),
  uncovered_items: z
    .array(z.object({ id: z.string(), title: z.string() }))
    .default([]),
});

export const ReportVerificationFunnelSchema = z.object({
  suspected: z.number().default(0),
  confirmed: z.number().default(0),
  flaky: z.number().default(0),
  not_reproduced: z.number().default(0),
});

export const ReportMetricsSchema = z.object({
  workflow_completion_pct: z.number().nullable().optional(),
  finding_verification_pct: z.number().nullable().optional(),
  evidence_completeness_pct: z.number().nullable().optional(),
});

export const ReportSchema = z.object({
  run: RunSchema,
  report_status: z.string().optional(),
  report_error: z.string().nullable().optional(),
  has_pdf: z.boolean().optional(),
  has_md: z.boolean().optional(),
  pdf_url: z.string().optional(),
  md_url: z.string().optional(),
  summary_counts: RunCountsSchema,
  verification_funnel: ReportVerificationFunnelSchema,
  spec_coverage: ReportSpecCoverageSchema,
  metrics: ReportMetricsSchema,
  review_log: z.array(ReviewDecisionSchema).default([]),
  budget_usage: BudgetUsageSchema,
  bugs: z.array(BugSchema).default([]),
});
export type Report = z.infer<typeof ReportSchema>;

// --- Config Defaults ---
export const ConfigDefaultsSchema = z.object({
  default_budgets: BudgetsSchema,
  limits: z.object({
    min_pages: z.number().default(1),
    max_pages: z.number().default(100),
    min_steps: z.number().default(5),
    max_steps: z.number().default(100),
    min_minutes: z.number().default(1),
    max_minutes: z.number().default(60),
    min_workers: z.number().default(1),
    max_workers: z.number().default(4),
  }),
  accepted_spec_extensions: z
    .array(z.string())
    .default([".md", ".txt", ".pdf", ".json", ".yaml", ".yml"]),
  max_spec_file_size_mb: z.number().default(10),
});
export type ConfigDefaults = z.infer<typeof ConfigDefaultsSchema>;

// --- Target Pre-Flight Check ---
export const TargetCheckResultSchema = z.object({
  reachable: z.boolean(),
  allowed: z.boolean(),
  reason: z.string().nullable().optional(),
  tls_valid: z.boolean().nullable().optional(),
  status_code: z.number().nullable().optional(),
});
export type TargetCheckResult = z.infer<typeof TargetCheckResultSchema>;

// --- Health ---
export const HealthStatusSchema = z.object({
  status: z.enum(["active", "degraded", "offline"]),
  workers_up: z.number().default(0),
  queue_depth: z.number().default(0),
  message: z.string().nullable().optional(),
});
export type HealthStatus = z.infer<typeof HealthStatusSchema>;

// --- Auth ---
export const AuthUserSchema = z.object({
  id: z.string(),
  username: z.string(),
  email: z.string().email().optional(),
  name: z.string().optional(),
  role: z.string().optional(),
});
export type AuthUser = z.infer<typeof AuthUserSchema>;

// --- SSE Real-Time Events ---
export const SSERunStatusEventSchema = z.object({
  type: z.literal("run.status"),
  status: RunStatusSchema,
  progress: z.number().default(0),
});

export const SSELogEventSchema = z.object({
  type: z.literal("log"),
  timestamp: z.string().optional(),
  level: z.enum(["info", "warn", "error", "debug"]).default("info"),
  source: z.string().optional(),
  message: z.string(),
});

export const SSECatalogReadyEventSchema = z.object({
  type: z.literal("catalog.ready"),
  tests: z.array(CatalogTestSchema),
});

export const SSEReviewDecisionEventSchema = z.object({
  type: z.literal("review.decision"),
  decision: ReviewDecisionSchema,
});

export const SSEWorkerUpdateEventSchema = z.object({
  type: z.literal("worker.update"),
  worker: WorkerSchema,
});

export const SSETestUpdateEventSchema = z.object({
  type: z.literal("test.update"),
  test: ExecutionTestSchema,
});

export const SSEBugSuspectedEventSchema = z.object({
  type: z.literal("bug.suspected"),
  bug: BugSchema,
});

export const SSEBugVerificationEventSchema = z.object({
  type: z.literal("bug.verification"),
  bug_id: z.string(),
  replay_index: z.number().min(1).max(3),
  result: ReplayResultSchema,
  duration_ms: z.number().nullable().optional(),
  video_url: z.string().nullable().optional(),
});

export const SSEBugFinalEventSchema = z.object({
  type: z.literal("bug.final"),
  bug: BugSchema,
});

export const SSEBudgetUpdateEventSchema = z.object({
  type: z.literal("budget.update"),
  usage: BudgetUsageSchema,
});

export const SSERunDoneEventSchema = z.object({
  type: z.literal("run.done"),
  run: RunSchema,
});

export const SSEEventSchema = z.discriminatedUnion("type", [
  SSERunStatusEventSchema,
  SSELogEventSchema,
  SSECatalogReadyEventSchema,
  SSEReviewDecisionEventSchema,
  SSEWorkerUpdateEventSchema,
  SSETestUpdateEventSchema,
  SSEBugSuspectedEventSchema,
  SSEBugVerificationEventSchema,
  SSEBugFinalEventSchema,
  SSEBudgetUpdateEventSchema,
  SSERunDoneEventSchema,
]);
export type SSEEvent = z.infer<typeof SSEEventSchema>;
