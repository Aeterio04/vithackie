# KAWACH (कवच) — Autonomous QA Testing Agent

> *"It doesn't just report bugs. It proves them."*

KAWACH is a production-grade, fully dynamic Next.js web frontend for an autonomous AI QA testing agent pipeline. It connects to a live FastAPI (Python) backend orchestrating specialized agents (**Explorer**, **Planner**, **Reviewer**, **Test Runner**, **Verifier**) on sandboxed Docker + Playwright workers.

Every number, list, status, log, screenshot, video, and report rendered in KAWACH originates from API responses.

---

## 🛡️ Core Verification Principle

A suspected bug becomes **Confirmed ONLY after 3 deterministic replays** conducted in isolated Docker sandboxes by a deterministic Playwright worker:
- **Confirmed**: 3 of 3 replays reproduce the defect. No LLM involved.
- **Flaky**: 1 to 2 of 3 replays reproduce.
- **Not reproduced**: 0 of 3 replays reproduce. Kept for engineering reference and not counted as a bug.

If an API response exhibits a discrepancy between a bug's status and its deterministic replay tally, KAWACH visibly displays a **Status mismatch** badge rather than masking or silently altering data.

---

## 🛠️ Technology Stack

- **Framework**: Next.js 16+ (App Router), React 19, TypeScript (strict mode, zero `any`)
- **Styling**: Tailwind CSS v4 with CSS-first `@theme` design tokens in `app/globals.css`
- **Design System**: Claude aesthetic (Warm Ivory `#FAF9F5`, Warm Cloud `#F0EEE6`, Card Border `#E3DACC`, Clay Orange Accent `#D97757`)
- **Typography**: `Newsreader` (headings & numbers), `Inter` (UI & tables), `JetBrains Mono` (logs, URLs, code)
- **State & Data**: TanStack Query (React Query) for caching, mutations, and polling; Zustand exclusively for lightweight UI state
- **Validation & Forms**: Zod domain schemas as single source of truth, React Hook Form
- **Real-time SSE**: Typed Server-Sent Events with cache updating, exponential backoff, Last-Event-ID resumption, and polling fallback
- **Accessibility**: Radix UI accessible primitives (`Dialog`, `Tabs`, `Tooltip`, `DropdownMenu`, `Checkbox`, `Switch`)

---

## 🚀 Getting Started

### 1. Installation

```bash
npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

Settings in `.env.local`:
```env
# Upstream FastAPI backend URL (Next.js rewrites /api/* to this address)
BACKEND_URL=http://localhost:8000

# Client-facing API base prefix
NEXT_PUBLIC_API_BASE_URL=/api

# Optional dev-only mock mode (mirrors all Zod schemas when backend is offline)
NEXT_PUBLIC_USE_MOCKS=false
```

> **Tip**: Toggle `NEXT_PUBLIC_USE_MOCKS=true` to test the entire application interface, interactive review gates, and live execution views in standalone mode without a running backend.

### 3. Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Production Build & Verification

```bash
npm run build
npm start
```

---

## 📂 Architecture & Directory Structure

```text
├── app/
│   ├── globals.css                       # Tailwind v4 @theme design tokens
│   ├── layout.tsx                        # Root layout with Newsreader, Inter & JetBrains Mono
│   ├── page.tsx                          # Dashboard (Hero start, KPIs, live execution, review gate)
│   ├── login/page.tsx                    # Cookie-based authentication page
│   ├── start/page.tsx                    # Full-page start test flow & V1 scope card
│   ├── catalog/                          # Catalog index & run picker
│   │   └── [runId]/page.tsx              # Test catalog table, review gate, and app map tree
│   ├── execution/                        # Execution index & run picker
│   │   └── [runId]/page.tsx              # Worker cards, 3x verification panel, streaming logs
│   ├── results/                          # Results index & run picker
│   │   ├── [runId]/page.tsx              # Bugs table with filter chips & preview drawer
│   │   └── [runId]/bugs/[bugId]/page.tsx # Bug detail, replay verdict card, evidence, repro.ts
│   ├── reports/                          # Reports index & run picker
│   │   └── [runId]/page.tsx              # Stacked div funnel, spec coverage, audit log, exports
│   └── api/
│       └── runs/[runId]/stream/route.ts  # Next.js unbuffered SSE proxy route handler
├── components/
│   ├── ui/                               # Reusable accessible UI components (Button, Card, Chip, Stepper, etc.)
│   ├── layout/                           # Sidebar, TopBar, and AppShell
│   ├── features/                         # StartTestForm with pre-flight checks and budgets
│   └── providers/                        # QueryClientProvider and ToastProvider
├── hooks/
│   └── useRunStream.ts                   # Real-time SSE hook with cache setQueryData and polling fallback
├── lib/
│   ├── api/                              # config.ts (endpoint constants), client.ts (typed fetch), hooks.ts
│   ├── mocks/                            # devMockService.ts (optional mock interceptor)
│   ├── store/                            # uiStore.ts (Zustand UI state)
│   └── utils.ts                          # Formatting and string utilities
├── types/
│   └── index.ts                          # Zod schemas & TypeScript domain types
└── docs/
    └── API_CONTRACT.md                   # Full FastAPI backend contract & SSE spec
```

---

## 🔌 API Contract Reference

See [`docs/API_CONTRACT.md`](./docs/API_CONTRACT.md) for full endpoint specifications, request payloads, response schemas, and SSE event formats to implement matching Pydantic models in FastAPI.
