/**
 * Dev-Only Mock Service (OFF by default)
 * Only activated when NEXT_PUBLIC_USE_MOCKS="true" in .env.local.
 * Strictly adheres to types/index.ts Zod schemas and FastAPI API contract.
 */

import {
  type Run,
  type CatalogTest,
  type Bug,
  type Worker,
  type Report,
  type ConfigDefaults,
  type HealthStatus,
  type TargetCheckResult,
} from "@/types";

const mockDefaults: ConfigDefaults = {
  default_budgets: {
    max_pages: 20,
    max_steps_per_test: 30,
    max_run_minutes: 15,
    parallel_workers: 2,
  },
  limits: {
    min_pages: 1,
    max_pages: 100,
    min_steps: 5,
    max_steps: 100,
    min_minutes: 1,
    max_minutes: 60,
    min_workers: 1,
    max_workers: 4,
  },
  accepted_spec_extensions: [".md", ".txt", ".pdf", ".json", ".yaml", ".yml"],
  max_spec_file_size_mb: 10,
};

const mockHealth: HealthStatus = {
  status: "active",
  workers_up: 4,
  queue_depth: 0,
  message: "Playwright cluster operational",
};

const mockRuns: Run[] = [
  {
    id: "run_01j7kawach_demo",
    target_url: "https://staging.storefront.internal",
    prompt: "Test user authentication, checkout cart, and payment gateway error handling",
    review_mode: "manual",
    status: "executing",
    progress: 68,
    created_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    finished_at: null,
    budgets: {
      max_pages: 20,
      max_steps_per_test: 30,
      max_run_minutes: 15,
      parallel_workers: 2,
    },
    budget_usage: {
      pages_crawled: 14,
      steps_executed: 82,
      elapsed_minutes: 8,
      active_workers: 2,
    },
    counts: {
      total_tests: 12,
      passed_tests: 9,
      failed_tests: 2,
      suspected_bugs: 3,
      confirmed_bugs: 2,
      flaky_bugs: 1,
      not_reproduced_bugs: 0,
      pending_reviews: 2,
    },
  },
];

let mockCatalog: CatalogTest[] = [
  {
    id: "test_auth_01",
    title: "User Sign-up with Valid Email & Password",
    spec_item_ids: ["AUTH-01", "SPEC-REQ-12"],
    steps: [
      "Navigate to https://staging.storefront.internal/signup",
      "Fill email input with timestamped test email",
      "Fill password with compliant string",
      "Click 'Create Account'",
    ],
    expected_result: "Redirected to /onboarding dashboard with HTTP 200",
    priority: "high",
    review_status: "approved",
    last_decision: {
      test_id: "test_auth_01",
      decision: "approved",
      actor: "human",
      reason: "Approved for smoke run",
      at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    },
  },
  {
    id: "test_checkout_02",
    title: "Apply Coupon Code During Active Session",
    spec_item_ids: ["CHECKOUT-03"],
    steps: [
      "Add item to cart",
      "Navigate to /checkout",
      "Enter promo code 'PROMO50'",
      "Verify discount calculation",
    ],
    expected_result: "Subtotal discounted by 50% without error banner",
    priority: "medium",
    review_status: "pending",
    last_decision: null,
  },
  {
    id: "test_payment_03",
    title: "Declined Card Handling & User Notification",
    spec_item_ids: ["PAY-09"],
    steps: [
      "Proceed to payment gateway",
      "Fill test card number 4000 0000 0000 0002",
      "Submit payment",
    ],
    expected_result: "Friendly decline message displayed; order remains pending",
    priority: "critical",
    review_status: "pending",
    last_decision: null,
  },
];

const mockBugs: Bug[] = [
  {
    id: "bug_promo_500",
    run_id: "run_01j7kawach_demo",
    title: "Server 500 error when applying special characters in coupon input",
    severity: "high",
    source: "test_runner",
    spec_item_ids: ["CHECKOUT-03"],
    status: "confirmed", // 3/3 reproduced
    replays: [
      {
        index: 1,
        result: "reproduced",
        duration_ms: 1250,
        timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      },
      {
        index: 2,
        result: "reproduced",
        duration_ms: 1190,
        timestamp: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
      },
      {
        index: 3,
        result: "reproduced",
        duration_ms: 1210,
        timestamp: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
      },
    ],
    steps_to_reproduce: [
      "Add any item to shopping cart",
      "Navigate to /checkout/payment",
      "Input coupon code '%^&*()'",
      "Click 'Apply'",
    ],
    expected: "Input validation error 'Invalid coupon characters'",
    actual: "Unhandled Internal Server Error 500 crash in checkout API",
    evidence: {
      screenshots: [],
      logs: "[Playwright] Error: POST /api/v1/coupons returned 500",
      console: ["Uncaught (in promise) Error: Server Error at checkout.js:142"],
      network: [],
    },
    repro_script_url: "/api/v1/artifacts/bug_promo_500_repro.ts",
    created_at: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
  },
  {
    id: "bug_cart_race",
    run_id: "run_01j7kawach_demo",
    title: "Rapid quantity increment results in out-of-sync subtotal",
    severity: "medium",
    source: "exploratory",
    spec_item_ids: ["CART-01"],
    status: "flaky", // 2 of 3
    replays: [
      {
        index: 1,
        result: "reproduced",
        duration_ms: 2100,
        timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
      },
      {
        index: 2,
        result: "not_reproduced",
        duration_ms: 2050,
        timestamp: new Date(Date.now() - 1 * 60 * 1000).toISOString(),
      },
      {
        index: 3,
        result: "reproduced",
        duration_ms: 2200,
        timestamp: new Date().toISOString(),
      },
    ],
    steps_to_reproduce: [
      "Click '+' button on cart item 5 times within 400ms",
      "Inspect subtotal text element",
    ],
    expected: "Subtotal reflects 5 units",
    actual: "Subtotal occasionally shows 4 units due to race condition",
    evidence: {
      screenshots: [],
      logs: "[Playwright] Debounce collision detected",
      console: [],
      network: [],
    },
    repro_script_url: "/api/v1/artifacts/bug_cart_race_repro.ts",
    created_at: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
  },
];

const mockWorkers: Worker[] = [
  {
    id: "worker-1",
    kind: "runner",
    current_test_id: "test_checkout_02",
    current_step: "Filling promo code",
    status: "running",
    latest_screenshot_url: null,
    screenshot_updated_at: new Date().toISOString(),
  },
  {
    id: "worker-2",
    kind: "runner",
    current_test_id: "test_payment_03",
    current_step: "Submitting payment form",
    status: "running",
    latest_screenshot_url: null,
    screenshot_updated_at: new Date().toISOString(),
  },
  {
    id: "worker-exp",
    kind: "exploratory",
    current_test_id: "exploratory_fuzz",
    current_step: "Fuzzing cart boundary inputs",
    status: "running",
    latest_screenshot_url: null,
    screenshot_updated_at: new Date().toISOString(),
  },
];

export function setupDevMockService() {
  if (typeof window === "undefined") return;
  if (process.env.NODE_ENV === "production" || process.env.NEXT_PUBLIC_USE_MOCKS !== "true") return;

  console.info("⚡ KAWACH Dev Mock Mode Active (NEXT_PUBLIC_USE_MOCKS=true)");

  const originalFetch = window.fetch;

  window.fetch = async function (input: RequestInfo | URL, init?: RequestInit) {
    const url = typeof input === "string" ? input : input.toString();

    // Health
    if (url.includes("/api/v1/health")) {
      return new Response(JSON.stringify(mockHealth), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Config defaults
    if (url.includes("/api/v1/config/defaults")) {
      return new Response(JSON.stringify(mockDefaults), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Stats
    if (url.includes("/api/v1/stats")) {
      return new Response(
        JSON.stringify({
          total_runs: mockRuns.length + 27,
          confirmed_bugs: 12,
          flaky_bugs: 4,
          pending_reviews: 2,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Auth me
    if (url.includes("/api/v1/auth/me")) {
      return new Response(
        JSON.stringify({
          id: "usr_mock",
          username: "paras_lead",
          name: "Paras Gajam",
          role: "Lead QA Engineer",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Login
    if (url.includes("/api/v1/auth/login")) {
      return new Response(
        JSON.stringify({
          id: "usr_mock",
          username: "paras_lead",
          name: "Paras Gajam",
          role: "Lead QA Engineer",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Target check
    if (url.includes("/api/v1/targets/check")) {
      return new Response(
        JSON.stringify({
          reachable: true,
          allowed: true,
          reason: null,
          tls_valid: true,
          status_code: 200,
        } as TargetCheckResult),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Spec upload
    if (url.includes("/api/v1/specs/upload")) {
      return new Response(
        JSON.stringify({
          spec_id: "spec_mock_1",
          filename: "spec.md",
          file_size_bytes: 4096,
          item_count: 5,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Runs list / create
    if (url.endsWith("/api/v1/runs")) {
      if (init?.method === "POST") {
        const body = JSON.parse(init.body as string);
        const newRun: Run = {
          id: `run_${Date.now().toString(36)}`,
          target_url: body.target_url,
          prompt: body.prompt || "",
          review_mode: body.review_mode || "manual",
          status: "exploring",
          progress: 5,
          created_at: new Date().toISOString(),
          finished_at: null,
          budgets: body.budgets || mockDefaults.default_budgets,
          budget_usage: {
            pages_crawled: 1,
            steps_executed: 0,
            elapsed_minutes: 0,
            active_workers: 1,
          },
          counts: {
            total_tests: 0,
            passed_tests: 0,
            failed_tests: 0,
            suspected_bugs: 0,
            confirmed_bugs: 0,
            flaky_bugs: 0,
            not_reproduced_bugs: 0,
            pending_reviews: 0,
          },
        };
        mockRuns.unshift(newRun);
        return new Response(JSON.stringify(newRun), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(mockRuns), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Run start
    if (url.includes("/start") && url.includes("/api/v1/runs/")) {
      const runId = url.split("/runs/")[1].split("/start")[0];
      const r = mockRuns.find((x) => x.id === runId) || mockRuns[0];
      r.status = "exploring";
      return new Response(JSON.stringify(r), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Run cancel
    if (url.includes("/cancel") && url.includes("/api/v1/runs/")) {
      const runId = url.split("/runs/")[1].split("/cancel")[0];
      const r = mockRuns.find((x) => x.id === runId) || mockRuns[0];
      r.status = "cancelled";
      return new Response(JSON.stringify(r), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Run retry
    if (url.includes("/retry") && url.includes("/api/v1/runs/")) {
      return new Response(JSON.stringify(mockRuns[0]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Catalog review
    if (url.includes("/review") && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      mockCatalog = mockCatalog.map((t) =>
        body.test_ids.includes(t.id)
          ? {
              ...t,
              review_status: body.decision,
              last_decision: {
                test_id: t.id,
                decision: body.decision,
                actor: "human",
                reason: body.reason || "",
                at: new Date().toISOString(),
              },
            }
          : t
      );
      return new Response(
        JSON.stringify({ applied_count: body.test_ids.length }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Catalog
    if (url.includes("/catalog")) {
      return new Response(JSON.stringify(mockCatalog), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Execution
    if (url.includes("/execution")) {
      return new Response(
        JSON.stringify({
          workers: mockWorkers,
          tests: [
            {
              id: "t_1",
              title: "User Sign-up with Valid Email & Password",
              status: "passed",
              duration_ms: 2450,
              worker_id: "worker-1",
            },
            {
              id: "t_2",
              title: "Apply Coupon Code During Active Session",
              status: "running",
              worker_id: "worker-1",
            },
          ],
          budget_usage: mockRuns[0].budget_usage,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Bugs
    if (url.includes("/bugs")) {
      return new Response(JSON.stringify(mockBugs), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Single bug
    if (url.includes("/api/v1/bugs/")) {
      const bugId = url.split("/bugs/")[1];
      const found = mockBugs.find((b) => b.id === bugId) || mockBugs[0];
      return new Response(JSON.stringify(found), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // App map
    if (url.includes("/app-map")) {
      return new Response(
        JSON.stringify({
          run_id: "run_01j7kawach_demo",
          total_pages: 5,
          max_pages_budget: 20,
          root_node: {
            id: "node_root",
            url: "https://staging.storefront.internal",
            title: "Storefront Home",
            depth: 0,
            status_code: 200,
            actions_found: ["button#login", "input#search", "a[href='/cart']"],
            children: [
              {
                id: "node_cart",
                url: "https://staging.storefront.internal/cart",
                title: "Shopping Cart",
                depth: 1,
                status_code: 200,
                actions_found: ["button#checkout", "button.quantity-increment"],
                children: [
                  {
                    id: "node_checkout",
                    url: "https://staging.storefront.internal/checkout",
                    title: "Checkout & Payment",
                    depth: 2,
                    status_code: 200,
                    actions_found: ["input#coupon", "button#pay-now"],
                  },
                ],
              },
            ],
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Report
    if (url.includes("/report")) {
      const report: Report = {
        run: mockRuns[0],
        summary_counts: mockRuns[0].counts!,
        verification_funnel: {
          suspected: 3,
          confirmed: 2,
          flaky: 1,
          not_reproduced: 0,
        },
        spec_coverage: {
          total_items: 6,
          covered_items: 5,
          covered_item_ids: [
            "AUTH-01",
            "SPEC-REQ-12",
            "CHECKOUT-03",
            "PAY-09",
            "CART-01",
          ],
          uncovered_items: [
            { id: "SEARCH-04", title: "Autocomplete search filter" },
          ],
        },
        metrics: {
          workflow_completion_pct: 92,
          finding_verification_pct: 100,
          evidence_completeness_pct: 100,
        },
        review_log: [
          {
            test_id: "test_auth_01",
            decision: "approved",
            actor: "human",
            reason: "Approved for smoke run",
            at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
          },
        ],
        budget_usage: mockRuns[0].budget_usage!,
        bugs: mockBugs,
      };
      return new Response(JSON.stringify(report), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Fallback single run
    if (url.includes("/api/v1/runs/")) {
      const r = mockRuns[0];
      return new Response(JSON.stringify(r), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    return originalFetch(input, init);
  };
}
