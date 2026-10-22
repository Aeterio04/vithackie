/**
 * CONTRACTS section 5: TypeScript types and interfaces.
 * Single source of truth for frontend, backend API, and runner.
 */

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
  | "failed";

export const STAGES: Stage[] = [
  "created",
  "exploring",
  "planning",
  "awaiting_review",
  "scripting",
  "running",
  "verifying",
  "reporting",
  "done",
  "failed",
];

export type Mode = "manual" | "autonomous";

export type Outcome = "passed" | "assertion_failure" | "test_error";

export type Category =
  | "validation"
  | "auth"
  | "data"
  | "navigation"
  | "console"
  | "network"
  | "ui"
  | "other";

export type Severity = "critical" | "high" | "medium" | "low";

export interface SpecItem {
  id: string; // e.g. "S1"
  text: string;
}

export interface Budgets {
  maxPages: number;
  exploreSeconds: number;
  maxTests: number;
  testTimeoutMs: number;
}

export interface RunInput {
  runId: string;
  createdAt: string;
  targetUrl: string;
  prompt: string;
  specRaw: string;
  spec: SpecItem[];
  username: string;
  mode: Mode;
  budgets: Budgets;
}

export interface RunProgress {
  step: string;
  done: number;
  total: number;
}

export interface StageTime {
  startedAt: string;
  endedAt: string | null;
}

export interface Run {
  runId: string;
  createdAt: string;
  updatedAt: string;
  stage: Stage;
  mode: Mode;
  targetUrl: string;
  error: string | null;
  progress: RunProgress | null;
  stageTimes: Record<string, StageTime>;
  golden: boolean;
}

export interface LlmUsage {
  calls: number;
  cacheHits: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
}

// ---- explorer ----
export interface FieldInfo {
  role: string;
  label: string;
  type: string;
  name: string;
  required: boolean;
}

export interface FormInfo {
  id: string; // e.g. "/signup#form0"
  action: string;
  method: string;
  submitText: string | null;
  fields: FieldInfo[];
}

export interface HeadingInfo {
  level: number;
  text: string;
}

export interface LinkInfo {
  text: string;
  href: string;
}

export interface ButtonInfo {
  text: string;
}

export interface PageInfo {
  url: string;
  path: string;
  title: string;
  status: number;
  requiresAuth: boolean;
  headings: HeadingInfo[];
  links: LinkInfo[];
  buttons: ButtonInfo[];
  forms: FormInfo[];
  consoleErrors: string[];
}

export interface Feature {
  name: string;
  description: string;
  pages: string[];
}

export interface LoginInfo {
  attempted: boolean;
  success: boolean;
  url: string | null;
  note: string | null;
}

export interface AppMapStats {
  pagesVisited: number;
  durationSeconds: number;
  budgetHit: "pages" | "time" | null;
}

export interface AppMap {
  baseUrl: string;
  generatedAt: string;
  login: LoginInfo;
  pages: PageInfo[];
  summary: string;
  features: Feature[];
  stats: AppMapStats;
  error: string | null;
}

// ---- planner / reviewer ----
export interface Step {
  n: number;
  action: string;
  expected: string | null;
}

export interface TestCase {
  id: string; // e.g. "T01"
  title: string;
  description: string;
  specRef: string[];
  priority: "high" | "medium" | "low";
  steps: Step[];
  status: "proposed" | "approved" | "rejected";
  origin: "planner" | "human" | "fallback";
  script: string | null; // e.g. "scripts/T05.spec.ts"
  scriptStatus: "pending" | "ok" | "error";
  scriptError: string | null;
}

export interface Catalog {
  runId: string;
  generatedAt: string;
  tests: TestCase[];
}

export interface ReviewDecision {
  testId: string;
  decision: "approve" | "reject";
  reason: string;
}

export interface ReviewLog {
  runId: string;
  reviewedAt: string;
  decisions: ReviewDecision[];
}

// ---- runner / triage ----
export interface TestResult {
  testId: string;
  title: string;
  file: string;
  source: "planned" | "exploratory";
  outcome: Outcome;
  durationMs: number;
  errorMessage: string | null;
  evidenceDir: string | null;
}

export interface ResultsSummary {
  total: number;
  passed: number;
  assertionFailures: number;
  testErrors: number;
}

export interface Results {
  runId: string;
  startedAt: string;
  durationSeconds: number;
  workers: number;
  tests: TestResult[];
  summary: ResultsSummary;
}

export interface Evidence {
  screenshot: string | null;
  video: string | null;
  trace: string | null;
  console: string | null;
  network: string | null;
}

export interface BugReplay {
  reproduced: number;
  attempts: number;
}

export interface Bug {
  id: string; // e.g. "B01"
  testId: string;
  source: "planned" | "exploratory";
  title: string;
  grep: string;
  file: string; // e.g. "scripts/T05.spec.ts"
  category: Category;
  severity: Severity;
  specRef: string[];
  steps: string[];
  expected: string;
  actual: string;
  errorMessage: string;
  signature: string;
  duplicates: string[];
  evidence: Evidence;
  status: "candidate" | "confirmed" | "flaky" | "not_reproduced";
  replay: BugReplay | null;
}

export interface BugsFile {
  runId: string;
  bugs: Bug[];
}

export interface VerificationAttempt {
  attempt: number;
  reproduced: boolean;
  outcome: Outcome;
  errorMessage: string | null;
  durationMs: number;
}

export interface Verification {
  bugId: string;
  verifiedAt: string;
  attempts: VerificationAttempt[];
  reproduced: number;
  status: "confirmed" | "flaky" | "not_reproduced";
}

export interface BlockedRequest {
  ts: string;
  testId: string;
  url: string;
  method: string;
  resourceType: string;
}

export interface ParallelTiming {
  workers1Seconds: number;
  workers4Seconds: number;
  speedup: number;
}

// ---- metrics / benchmark ----
export interface MetricsTests {
  planned: number;
  approved: number;
  passed: number;
  failed: number;
  errored: number;
}

export interface MetricsBugs {
  candidates: number;
  confirmed: number;
  flaky: number;
  notReproduced: number;
}

export interface MetricsCoverage {
  pagesInMap: number;
  pagesExercised: number;
  formsInMap: number;
  formsExercised: number;
  specItems: number;
  specItemsCovered: number;
}

export interface MetricsSafety {
  blockedRequests: number;
}

export interface Metrics {
  runId: string;
  wallClockSeconds: number;
  stageSeconds: Record<string, number>;
  tests: MetricsTests;
  bugs: MetricsBugs;
  coverage: MetricsCoverage;
  llm: LlmUsage;
  parallel: ParallelTiming | null;
  safety: MetricsSafety;
}

export interface BenchmarkMatch {
  bugId: string;
  groundTruthId: string | null; // null = false positive
}

export interface Benchmark {
  runId: string;
  groundTruthTotal: number;
  matches: BenchmarkMatch[];
  truePositives: number;
  falsePositives: number;
  recall: number;
  precision: number;
  replayRate: number;
}

// ---- API views ----
export interface RunView {
  run: Run;
  input: RunInput;
  appMap: AppMap | null;
  catalog: Catalog | null;
  reviewLog: ReviewLog | null;
  results: Results | null;
  bugs: Bug[];
  verifications: Verification[];
  metrics: Metrics | null;
  hasReport: boolean;
}

export interface RunListItemCounts {
  tests: number;
  bugs: number;
  confirmed: number;
  flaky: number;
}

export interface RunListItem {
  runId: string;
  createdAt: string;
  stage: Stage;
  mode: Mode;
  targetUrl: string;
  counts: RunListItemCounts;
}
