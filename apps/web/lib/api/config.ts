/**
 * API Endpoints Configuration
 * Single source of truth for all API routes.
 * Prefixed with /api/v1 - easily customizable for backend alignment.
 */

export const API_BASE_PREFIX = "/api/v1";

export const API_ENDPOINTS = {
  // Auth
  AUTH_LOGIN: `${API_BASE_PREFIX}/auth/login`,
  AUTH_LOGOUT: `${API_BASE_PREFIX}/auth/logout`,
  AUTH_ME: `${API_BASE_PREFIX}/auth/me`,

  // System & Config
  HEALTH: `${API_BASE_PREFIX}/health`,
  CONFIG_DEFAULTS: `${API_BASE_PREFIX}/config/defaults`,
  STATS: `${API_BASE_PREFIX}/stats`,

  // Pre-flight check
  TARGETS_CHECK: `${API_BASE_PREFIX}/targets/check`,

  // Specs
  SPECS_UPLOAD: `${API_BASE_PREFIX}/specs/upload`,

  // Runs
  RUNS: `${API_BASE_PREFIX}/runs`,
  RUN_BY_ID: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}`,
  RUN_START: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/start`,
  RUN_CANCEL: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/cancel`,
  RUN_RETRY: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/retry`,

  // Real-time & Polling
  // Note: Stream route in Next.js goes through /api/runs/:runId/stream route handler
  RUN_STREAM: (runId: string) => `/api/runs/${runId}/stream`,
  RUN_EVENTS_POLL: (runId: string, sinceCursor?: string) =>
    `${API_BASE_PREFIX}/runs/${runId}/events${sinceCursor ? `?since=${encodeURIComponent(sinceCursor)}` : ""}`,

  // App Map & Discovered Pages
  RUN_APP_MAP: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/app-map`,

  // Test Catalog & Review
  RUN_CATALOG: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/catalog`,
  RUN_CATALOG_TEST: (runId: string, testId: string) =>
    `${API_BASE_PREFIX}/runs/${runId}/catalog/${testId}`,
  RUN_REVIEW: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/review`,
  RUN_REVIEW_LOG: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/review-log`,

  // Execution & Workers
  RUN_EXECUTION: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/execution`,
  RUN_TESTS: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/tests`,

  // Bugs
  RUN_BUGS: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/bugs`,
  BUG_BY_ID: (bugId: string) => `${API_BASE_PREFIX}/bugs/${bugId}`,

  // Reports & Exports
  RUN_REPORT: (runId: string) => `${API_BASE_PREFIX}/runs/${runId}/report`,
  RUN_REPORT_EXPORT: (
    runId: string,
    format: "html" | "pdf" | "json" | "csv" = "json"
  ) => `${API_BASE_PREFIX}/runs/${runId}/report/export?format=${format}`,
  RUN_TESTS_EXPORT: (runId: string) =>
    `${API_BASE_PREFIX}/runs/${runId}/tests/export`,
} as const;
