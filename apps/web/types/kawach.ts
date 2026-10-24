import type { ReviewMode, Budgets, BudgetUsage, RunCounts } from "./index";
export * from "./index";

export type Stage =
  | "created"
  | "exploring"
  | "planning"
  | "awaiting_review"
  | "scripting"
  | "running"
  | "verifying"
  | "reporting"
  | "done"
  | "failed"
  | "cancelled";

export interface RunProgress {
  stage: Stage;
  step: string;
  done: number;
  total: number;
}

export interface WorkerInfo {
  worker_id: string;
  workerId?: string;
  status: "busy" | "idle" | "running" | "error";
  current_test: string | null;
  currentTest?: string | null;
  elapsed_s: number;
  latest_screenshot_url?: string | null;
}

export interface ExecutionSnapshot {
  active_workers: number;
  workers: WorkerInfo[];
}

export interface LogLine {
  id: string;
  timestamp: string;
  level: "debug" | "info" | "warn" | "error";
  source: string;
  message: string;
  line: string;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  type: string;
  summary: string;
  metadata?: Record<string, unknown>;
}

export interface KawachRun {
  id: string;
  runId?: string;
  target_url: string;
  targetUrl?: string;
  project_id?: string;
  projectId?: string;
  stage: Stage;
  status?: string;
  mode: ReviewMode;
  created_at: string;
  createdAt?: string;
  finished_at?: string | null;
  finishedAt?: string | null;
  prompt?: string;
  progress?: RunProgress;
  counts?: any;
  budgets?: any;
  budget_usage?: any;
  metrics?: any;
  error?: string;
}
