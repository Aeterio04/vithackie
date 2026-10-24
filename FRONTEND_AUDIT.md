# KAWACH Frontend Architecture & Quality Audit Report

> **Target Repository:** `kawach` (Frontend in `apps/web`)  
> **Auditor Role:** Senior Frontend Auditor  
> **Reference Specifications:** `design.md` (v1.0 Design System & Blueprint) and `FRONTEND_DEVELOPMENT_GUIDE.md` (API Reference)  
> **Document Status Note:** Both reference documents (`design.md` and `FRONTEND_DEVELOPMENT_GUIDE.md`) were located and verified in git stash revision (`stash@{0}: stash-before-checkout-paras`). Their full contents have been extracted and referenced as the binding target specification for this audit.

---

## 1. STACK & TOOLING

### Core Framework & Runtime
- **Frontend Root Path:** `apps/web`
- **Framework & Version:** Next.js `16.4.2` (`"next": "16.4.2"`)
- **React Version:** React `19.3.0` (`"react": "19.3.0"`, `"react-dom": "19.3.0"`)
- **TypeScript:** Yes, version `^5.0.0`
  - Strict mode enabled (`"strict": true` in `tsconfig.json`)
  - Target: `ES2017`, Module: `esnext`, Resolution: `bundler`
  - Path mapping: `"@/*": ["./src/*", "./*"]` (Causes duplicate and ambiguous import resolution)
- **Router Type:** Next.js App Router (`apps/web/src/app`)
- **Package Manager & Lockfile:** `npm` (`package-lock.json` present, 7,917 lines). `pnpm` is specified by `design.md` but is NOT currently used; no `pnpm-lock.yaml`.

### Dependencies & DevDependencies
| Package Name | Declared Version | Type | Notes |
| :--- | :--- | :--- | :--- |
| `@hookform/resolvers` | `^5.9.2` | dependency | Form validation integration |
| `@radix-ui/react-checkbox` | `^1.4.1` | dependency | Accessible primitive |
| `@radix-ui/react-dialog` | `^1.3.1` | dependency | Accessible primitive |
| `@radix-ui/react-dropdown-menu` | `^2.2.1` | dependency | Accessible primitive |
| `@radix-ui/react-switch` | `^1.4.1` | dependency | Accessible primitive |
| `@radix-ui/react-tabs` | `^1.2.1` | dependency | Accessible primitive |
| `@radix-ui/react-tooltip` | `^1.4.1` | dependency | Accessible primitive |
| `@tanstack/react-query` | `^5.104.4` | dependency | Server state & query cache |
| `clsx` | `^2.1.1` | dependency | Class string helper |
| `lucide-react` | `^1.59.0` | dependency | UI iconography |
| `next` | `16.4.2` | dependency | Core meta-framework |
| `react` | `19.3.0` | dependency | Core UI library |
| `react-dom` | `19.3.0` | dependency | DOM rendering |
| `react-hook-form` | `^7.90.0` | dependency | Form state management |
| `tailwind-merge` | `^3.7.0` | dependency | Conflict-free class merging |
| `zod` | `^4.6.7` | dependency | Schema validation & typing |
| `zustand` | `^5.0.15` | dependency | Client UI state |
| `@tailwindcss/turbopack` | `^4` | devDependency | Tailwind v4 Turbopack loader |
| `@types/node` | `^20` | devDependency | TypeScript node typings |
| `@types/react` | `^19` | devDependency | React 19 typings |
| `@types/react-dom` | `^19` | devDependency | React-DOM 19 typings |
| `eslint` | `^9` | devDependency | Linter engine |
| `eslint-config-next` | `16.4.2` | devDependency | Next.js eslint ruleset |
| `tailwindcss` | `^4` | devDependency | Utility CSS framework v4 |
| `typescript` | `^5` | devDependency | Type checking |

### Scripts (`package.json`)
```json
"scripts": {
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "eslint",
  "types": "openapi-typescript ../../packages/contracts/openapi.json -o src/generated/api-types.ts"
}
```

### Styling & Ecosystem Presence
- **Tailwind Version:** Tailwind CSS v4 (`tailwindcss: "^4"`, `@tailwindcss/turbopack: "^4"`).
- **Tailwind Config Style:** Inline `@theme` inside `src/app/globals.css`. There is NO `tailwind.config.js` or `tailwind.config.ts`.
- **PostCSS Config:** **NOT FOUND** (no `postcss.config.js` or `postcss.config.mjs`).
- **shadcn/ui Configuration:** **NOT FOUND** (`components.json` is missing).
- **Radix Packages:** 6 packages installed (`checkbox`, `dialog`, `dropdown-menu`, `switch`, `tabs`, `tooltip`).
- **Icon Library:** `lucide-react`.
- **Chart Library:** **NOT FOUND** (`recharts` specified in `design.md` §14.3 is absent; inline SVG bars and donuts are hardcoded).
- **State & Data Libs:** `@tanstack/react-query` (v5.104.4), `zustand` (v5.0.15), native `fetch`. (No Redux, no SWR, no Axios).
- **Form Libraries:** `react-hook-form` (v7.90.0) + `@hookform/resolvers` (v5.9.2).
- **Zod:** `zod` (`^4.6.7`).
- **Lint / Format / Test Setup:**
  - `eslint`: Present (`eslint.config.mjs` flat config).
  - `prettier`: **NOT FOUND**.
  - `vitest` / `jest`: **NOT FOUND**.
  - `playwright`: **NOT FOUND**.
  - `storybook`: **NOT FOUND**.
- **Missing Required Target Dependencies:**
  `cmdk`, `sonner`, `motion`, `recharts`, `d3-force`, `shiki`, `react-markdown`, `rehype-sanitize`, `remark-gfm`, `date-fns`, `geist`, `@tanstack/react-virtual`, `@tanstack/react-query-devtools`.

### Environment Variables & Backend URL Configuration
- **Environment Variable Names Used:**
  - `BACKEND_URL`: Used in `apps/web/next.config.ts` (defaults to `http://localhost:8000`).
  - `NEXT_PUBLIC_API_URL`: Used in `apps/web/src/shared/lib/api/config.ts` and `apps/web/lib/api/config.ts` (defaults to `/api/v1`).
  - `NEXT_PUBLIC_USE_MOCKS`: Used in `apps/web/middleware.ts` and `devMockService.ts`.
  - `NEXT_PUBLIC_MOCK_DELAY_MS`: Used in `devMockService.ts`.
  - `NEXT_PUBLIC_MOCK_RUN_ID`: Used in `devMockService.ts`.
- **Backend URL & Proxy Configuration:**
  - `next.config.ts` defines rewrites:
    `source: "/api/:path*"` -> `destination: "${backendUrl}/api/:path*"`.
  - When the client requests `/api/v1/health`, Next.js rewrites it directly to `http://localhost:8000/api/v1/health`.
  - Same-origin proxy is active, but CORS/cookie handling relies entirely on `credentials: "include"`.

---

## 2. FOLDER TREE

### Directory Structure (Depth 4)
```text
apps/web/
├── components/                            # [DUPLICATE] Legacy root components directory
│   ├── features/                          # Feature forms (StartTestForm)
│   ├── layout/                            # Layout shells (AppShell, Sidebar, TopBar)
│   ├── providers/                         # Empty 3-line stub QueryProvider
│   └── ui/                                # 23 UI primitives duplicated with src/shared/ui/
├── hooks/                                 # [DUPLICATE] useRunStream.ts duplicated with src/shared/hooks/
├── lib/                                   # [DUPLICATE] API client, hooks, mocks, store, utils
│   ├── api/                               # client.ts, config.ts, hooks.ts
│   ├── mocks/                             # devMockService.ts (620 lines)
│   └── store/                             # uiStore.ts
├── public/                                # Static SVGs (file, globe, next, vercel, window)
├── src/                                   # Application source tree
│   ├── app/                               # App router pages & layouts
│   │   ├── (app)/                         # Authenticated application group
│   │   │   └── projects/                  # Projects pages (list, new, [id], commits, settings, tests)
│   │   ├── (auth)/                        # Authentication routes
│   │   │   ├── login/                     # Login page
│   │   │   └── register/                  # Register page
│   │   ├── catalog/                       # Catalog route group (/catalog, /catalog/[runId])
│   │   ├── debug/                         # Diagnostic routes
│   │   │   └── connection/                # SSE & health probe page
│   │   ├── execution/                     # Execution route group (/execution, /execution/[runId])
│   │   ├── reports/                       # Report route group (/reports, /reports/[runId])
│   │   ├── results/                       # Results route group (/results, /results/[runId], /bugs/[bugId])
│   │   └── start/                         # Run creation wizard entrypoint
│   ├── features/                          # Feature domains
│   │   ├── auth/                          # Auth components & API
│   │   ├── catalog/                       # CatalogView component (897 LOC)
│   │   ├── commits/                       # CommitEmptyState
│   │   ├── library/                       # SavedTestEmptyState
│   │   ├── projects/                      # Project components, settings, and CRUD API
│   │   ├── reports/                       # ReportView component (717 LOC)
│   │   └── results/                       # BugDetailView (525 LOC), ResultsView (513 LOC)
│   ├── generated/                         # OpenAPI generated types
│   │   └── api-types.ts                   # Generated TypeScript types (5,105 LOC)
│   └── shared/                            # [DUPLICATE] Shared components, hooks, lib
│       ├── hooks/                         # useRunStream.ts (384 LOC)
│       ├── layout/                        # AppShell, Sidebar, TopBar
│       ├── lib/                           # client, config, hooks, devMockService, uiStore, utils
│       ├── providers/                     # QueryProvider with QueryClient
│       └── ui/                            # 23 UI primitive components
├── types/                                 # Central domain schema & types (498 LOC)
├── eslint.config.mjs                      # ESLint flat config
├── middleware.ts                          # Next.js session route protection middleware
├── next.config.ts                         # Next.js configuration & API proxy rewrites
├── package.json                           # NPM dependencies & scripts
└── tsconfig.json                          # TypeScript configuration
```

### Folder Annotations under `src/`
- `src/app/`: App router page entrypoints, group layouts, and global styles (`globals.css`).
- `src/features/`: Domain-specific components, queries, and UI views split by domain (`auth`, `catalog`, `commits`, `library`, `projects`, `reports`, `results`).
- `src/generated/`: Auto-generated OpenAPI TypeScript contracts (`api-types.ts`).
- `src/shared/`: Shared layout components, UI primitives, API client, custom hooks, and mock services (largely cloned from root `components/`, `lib/`, `hooks/`).

### File Count & Line Breakdown
| Top-Level Folder | .tsx | .ts | .json | .css | .mjs | .md | .svg/.ico | Total Files | Total LOC |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `apps/web/` (root) | 0 | 2 | 2 | 0 | 1 | 1 | 0 | 6 | 8,086 |
| `components/` | 28 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 2,752 |
| `hooks/` | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 384 |
| `lib/` | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 6 | 1,615 |
| `public/` | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 5 | 5 |
| `src/` | 60 | 16 | 0 | 1 | 0 | 0 | 1 | 78 | 15,638 |
| `types/` | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 498 |
| **TOTAL** | **88** | **26** | **2** | **1** | **1** | **1** | **6** | **126** | **28,978** |

### Top 15 Largest Source Files (Excluding Lockfiles)
| Rank | File Path | Extension | Lines of Code (LOC) | Concern |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `src/generated/api-types.ts` | `.ts` | 5,105 | Auto-generated OpenAPI contracts |
| 2 | `src/features/catalog/components/CatalogView.tsx` | `.tsx` | 897 | Giant catalog review & test editor table |
| 3 | `src/app/page.tsx` | `.tsx` | 754 | Monolithic home dashboard + live controller |
| 4 | `src/features/reports/components/ReportView.tsx` | `.tsx` | 717 | Report dashboard, export links, KPI metrics |
| 5 | `components/features/StartTestForm.tsx` | `.tsx` | 623 | Monolithic wizard form with specs & limits |
| 6 | `lib/mocks/devMockService.ts` | `.ts` | 620 | Dev mock simulation service |
| 7 | `src/shared/lib/mocks/devMockService.ts` | `.ts` | 620 | Duplicate dev mock simulation service |
| 8 | `src/features/results/components/BugDetailView.tsx` | `.tsx` | 525 | Bug detail view with 3-trial pips & evidence |
| 9 | `lib/api/hooks.ts` | `.ts` | 517 | TanStack Query hook definitions |
| 10 | `src/shared/lib/api/hooks.ts` | `.ts` | 517 | Duplicate TanStack Query hook definitions |
| 11 | `src/features/results/components/ResultsView.tsx` | `.tsx` | 513 | Bug ledger with filters & replay status |
| 12 | `types/index.ts` | `.ts` | 498 | Central TypeScript interfaces & Zod schemas |
| 13 | `hooks/useRunStream.ts` | `.ts` | 384 | SSE connection & cache invalidation hook |
| 14 | `src/shared/hooks/useRunStream.ts` | `.ts` | 384 | Duplicate SSE connection & cache hook |
| 15 | `src/app/debug/connection/page.tsx` | `.tsx` | 374 | Connection & SSE test probe interface |

---

## 3. ROUTE / PAGE INVENTORY

### Current Route Inventory Table
| Route URL | File Path | Purpose | API Endpoints Used | Data Fetching | Client / Server | Approx LOC | Main Child Components |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/` | `src/app/page.tsx` | Combined Dashboard, Run Creation, Active Run Hub & SSE monitor | `/api/v1/runs`, `/api/v1/stats`, `/api/v1/catalog`, `/api/v1/bugs` | `useRuns`, `useStats`, `useRunStream` | Client | 754 | `RunSwitcher`, `Stepper`, `BudgetMeter`, `LogViewer`, `Button`, `DataTable` |
| `/catalog` | `src/app/catalog/page.tsx` | Runs listing to redirect to specific catalog | `/api/v1/runs` | `useRuns` | Client | 108 | `EmptyState`, `Button`, `Chip`, `Skeleton` |
| `/catalog/[runId]` | `src/app/catalog/[runId]/page.tsx` | Stub wrapper for Catalog review gate | None (delegated) | Child component queries | Client | 7 | `CatalogView` |
| `/debug/connection` | `src/app/debug/connection/page.tsx` | Manual API & SSE probe diagnostics | `/api/v1/health`, `/api/v1/stats`, `/api/v1/auth/me`, `/api/v1/runs/test-probe-sse/stream` | Raw `fetch` & `EventSource` | Client | 374 | `Terminal`, `CheckCircle2`, `XCircle`, `Button` |
| `/execution` | `src/app/execution/page.tsx` | Runs listing to select execution cockpit | `/api/v1/runs` | `useRuns` | Client | 119 | `EmptyState`, `Button`, `Chip`, `Skeleton` |
| `/execution/[runId]` | `src/app/execution/[runId]/page.tsx` | Stub wrapper for execution cockpit | None | Broken Import | Client | 7 | `ExecutionCockpit` (**Broken Import**) |
| `/login` | `src/app/(auth)/login/page.tsx` | User login wrapper | None (delegated) | Child component mutation | Client | 14 | `LoginForm` |
| `/projects` | `src/app/(app)/projects/page.tsx` | Project list wrapper | None (delegated) | Child component queries | Client | 12 | `ProjectList` |
| `/projects/[projectId]` | `src/app/(app)/projects/[projectId]/page.tsx` | Single project details & project runs | `/api/v1/projects/${id}`, `/api/v1/runs` | `apiClient.get`, `useRuns` | Client | 186 | `Button`, `Play`, `Bookmark`, `GitCommit` |
| `/projects/[projectId]/commits` | `src/app/(app)/projects/[projectId]/commits/page.tsx` | Git commit analysis stub | None | None (static) | Client | 17 | `CommitEmptyState` |
| `/projects/[projectId]/settings` | `src/app/(app)/projects/[projectId]/settings/page.tsx` | Project configuration & credentials | None (delegated) | Child component queries | Client | 17 | `ProjectSettings` |
| `/projects/[projectId]/tests` | `src/app/(app)/projects/[projectId]/tests/page.tsx` | Saved tests repository stub | None | None (static) | Client | 17 | `SavedTestEmptyState` |
| `/projects/new` | `src/app/(app)/projects/new/page.tsx` | New project & test creation tabs | None (delegated) | Broken Import / Client | Client | 61 | `NewProjectForm`, `StartTestForm` (**Broken Import**) |
| `/register` | `src/app/(auth)/register/page.tsx` | User registration wrapper | None (delegated) | Child component mutation | Client | 14 | `RegisterForm` |
| `/reports` | `src/app/reports/page.tsx` | Runs listing to select report view | `/api/v1/runs` | `useRuns` | Client | 113 | `EmptyState`, `Button`, `Chip`, `Skeleton` |
| `/reports/[runId]` | `src/app/reports/[runId]/page.tsx` | Stub wrapper for Executive Report | None (delegated) | Child component queries | Client | 7 | `ReportView` |
| `/results` | `src/app/results/page.tsx` | Runs listing to select bug results | `/api/v1/runs` | `useRuns` | Client | 113 | `EmptyState`, `Button`, `Chip`, `Skeleton` |
| `/results/[runId]` | `src/app/results/[runId]/page.tsx` | Stub wrapper for Bug ledger | None (delegated) | Child component queries | Client | 7 | `ResultsView` |
| `/results/[runId]/bugs/[bugId]` | `src/app/results/[runId]/bugs/[bugId]/page.tsx` | Stub wrapper for Bug detail & replay | None (delegated) | Child component queries | Client | 7 | `BugDetailView` |
| `/start` | `src/app/start/page.tsx` | Standalone Run creation wizard | None (delegated) | Child component mutation | Client | 105 | `StartTestForm` |

### Special Application Files
- **Layouts:** `src/app/layout.tsx` (Root layout only). No nested group layouts (`(app)/layout.tsx` or `(auth)/layout.tsx`) exist.
- **Loading Files (`loading.tsx`):** **NOT FOUND** (0 exist across the entire app).
- **Error Boundaries (`error.tsx`, `global-error.tsx`):** **NOT FOUND** (0 exist across the entire app).
- **Not Found Surfaces (`not-found.tsx`):** **NOT FOUND** (0 exist across the entire app).
- **Middleware:** `apps/web/middleware.ts` (Protects non-auth routes using regex and cookie checks).

### Unreachable and Duplicate Pages
- **Duplicated Run Pickers:** `/catalog`, `/execution`, `/reports`, `/results` are 4 nearly identical duplicate pages that query `useRuns()` and render a list of runs to redirect to `/[runId]`.
- **Orphan / Disconnected Pages:** `/projects/[projectId]/commits` and `/projects/[projectId]/tests` render empty stubs with no backend endpoints backing them.
- **Unreachable Broken Route:** `/execution/[runId]` crashes on mount due to missing `@/features/runs/components/ExecutionCockpit`.

### Route Comparison vs `design.md` §10
| Route in `design.md` §10 | Status in Current Codebase | Current File Path | Mismatch Details |
| :--- | :--- | :--- | :--- |
| `10.1 /` Dashboard | **EXISTS (UNSTRUCTURED)** | `src/app/page.tsx` | Monolithic 754-line file mixing Dashboard, Run Switcher, Live Monitor, and Review Gate |
| `10.2 /login` & `/register` | **EXISTS** | `src/app/(auth)/login/page.tsx`, `register/page.tsx` | Matches target route URLs |
| `10.3 /projects` | **EXISTS** | `src/app/(app)/projects/page.tsx` | Matches target route URL |
| `10.4 /projects/[id]` | **EXISTS** | `src/app/(app)/projects/[projectId]/page.tsx` | Folder name uses `[projectId]` instead of target `[id]` |
| `10.5 /runs/new` (Wizard) | **SCATTERED** | `src/app/start/page.tsx` & `(app)/projects/new/page.tsx` | Lives at `/start` instead of target `/runs/new` |
| `10.6 /runs` & `/runs/[id]` (Hub) | **SCATTERED** | `src/app/page.tsx` & `src/app/execution/[runId]/page.tsx` | Hub is bundled inside `/` or points to non-existent cockpit |
| `10.7 /runs/[id]/catalog` | **SCATTERED** | `src/app/catalog/[runId]/page.tsx` | Lives at `/catalog/[runId]` instead of sub-route `/runs/[id]/catalog` |
| `10.8 /runs/[id]/live` | **SCATTERED** | `src/app/execution/[runId]/page.tsx` | Lives at `/execution/[runId]` instead of sub-route `/runs/[id]/live` |
| `10.9 /runs/[id]/bugs` | **SCATTERED** | `src/app/results/[runId]/page.tsx` | Lives at `/results/[runId]` instead of sub-route `/runs/[id]/bugs` |
| `10.10 /runs/[id]/bugs/[bugId]` | **SCATTERED** | `src/app/results/[runId]/bugs/[bugId]/page.tsx` | Lives at `/results/[runId]/bugs/[bugId]` instead of `/runs/[id]/bugs/[bugId]` |
| `10.11 /runs/[id]/sitemap` (App Map) | **MISSING** | **NOT FOUND** | No App Map page exists anywhere in the router |
| `10.12 /runs/[id]/report` | **SCATTERED** | `src/app/reports/[runId]/page.tsx` | Lives at `/reports/[runId]` instead of sub-route `/runs/[id]/report` |
| `10.13 /runs/[id]/timeline` | **MISSING** | **NOT FOUND** | No audit/timeline ledger page exists |
| `10.14 /settings` | **MISSING** | **NOT FOUND** | Only project-level `/projects/[projectId]/settings` exists |
| `10.15 Global error surfaces` | **MISSING** | **NOT FOUND** | `not-found.tsx`, `error.tsx`, `global-error.tsx` are missing |
| *Extra: `/projects/[projectId]/commits`* | **EXTRA / UNMATCHED** | `src/app/(app)/projects/[projectId]/commits/page.tsx` | Not specified in `design.md` |
| *Extra: `/projects/[projectId]/tests`* | **EXTRA / UNMATCHED** | `src/app/(app)/projects/[projectId]/tests/page.tsx` | Not specified in `design.md` |
| *Extra: `/debug/connection`* | **EXTRA / UNMATCHED** | `src/app/debug/connection/page.tsx` | Diagnostic helper, not in `design.md` |

---

## 4. COMPONENT INVENTORY

### All Component Files & Importer Audit
| File Path | Exported Name(s) | LOC | Importer Count | Category Guess | Issues Detected |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `components/features/StartTestForm.tsx` | `StartTestForm` | 623 | 3 | Domain Form | Giant component (>250 LOC), hardcoded hex colors |
| `components/layout/AppShell.tsx` | `AppShell` | 27 | 1 | Layout | Duplicate of `src/shared/layout/AppShell.tsx` |
| `components/layout/Sidebar.tsx` | `Sidebar` | 202 | 2 | Layout | Duplicate of `src/shared/layout/Sidebar.tsx`, cursive inline font |
| `components/layout/TopBar.tsx` | `TopBar` | 168 | 2 | Layout | Duplicate of `src/shared/layout/TopBar.tsx` |
| `components/providers/QueryProvider.tsx` | None (empty) | 3 | 1 | Provider | Broken stub re-export |
| `components/ui/BudgetMeter.tsx` | `BudgetMeter` | 61 | 1 | Primitive UI | Duplicate of `src/shared/ui/BudgetMeter.tsx` |
| `components/ui/Button.tsx` | `Button` | 62 | 20 | Primitive UI | Duplicate of `src/shared/ui/Button.tsx` |
| `components/ui/Card.tsx` | `Card`, `CardHeader`, `CardTitle` | 52 | 0 | Primitive UI | Unused (0 importers), duplicate of `src/shared/ui/Card.tsx` |
| `components/ui/Checkbox.tsx` | `Checkbox` | 27 | 3 | Primitive UI | Duplicate of `src/shared/ui/Checkbox.tsx` |
| `components/ui/Chip.tsx` | `Chip` | 90 | 13 | Primitive UI | Duplicate of `src/shared/ui/Chip.tsx` |
| `components/ui/CodeBlock.tsx` | `CodeBlock` | 111 | 1 | Primitive UI | Duplicate of `src/shared/ui/CodeBlock.tsx` |
| `components/ui/ConnectionBadge.tsx` | `ConnectionBadge` | 41 | 0 | Primitive UI | Unused (0 importers), duplicate of `src/shared/ui/ConnectionBadge.tsx` |
| `components/ui/DataTable.tsx` | `DataTable` | 100 | 0 | Primitive UI | Unused (0 importers), duplicate of `src/shared/ui/DataTable.tsx` |
| `components/ui/Dialog.tsx` | `Dialog`, `DialogContent`, etc. | 102 | 2 | Primitive UI | Duplicate of `src/shared/ui/Dialog.tsx` |
| `components/ui/Drawer.tsx` | `Drawer` | 97 | 2 | Primitive UI | Duplicate of `src/shared/ui/Drawer.tsx` |
| `components/ui/DropdownMenu.tsx` | `DropdownMenu`, etc. | 55 | 5 | Primitive UI | Duplicate of `src/shared/ui/DropdownMenu.tsx` |
| `components/ui/EmptyState.tsx` | `EmptyState` | 43 | 9 | Primitive UI | Duplicate of `src/shared/ui/EmptyState.tsx` |
| `components/ui/FileDropzone.tsx` | `FileDropzone` | 184 | 1 | Primitive UI | Duplicate of `src/shared/ui/FileDropzone.tsx` |
| `components/ui/LogViewer.tsx` | `LogViewer` | 176 | 1 | Primitive UI | Duplicate of `src/shared/ui/LogViewer.tsx` |
| `components/ui/ReplayPips.tsx` | `ReplayPips` | 112 | 4 | Primitive UI | Duplicate of `src/shared/ui/ReplayPips.tsx` |
| `components/ui/RunSwitcher.tsx` | `RunSwitcher` | 108 | 2 | Primitive UI | Duplicate of `src/shared/ui/RunSwitcher.tsx` |
| `components/ui/Skeleton.tsx` | `Skeleton` | 17 | 11 | Primitive UI | Duplicate of `src/shared/ui/Skeleton.tsx` |
| `components/ui/Stepper.tsx` | `Stepper` | 90 | 3 | Primitive UI | Duplicate of `src/shared/ui/Stepper.tsx`, 6 stages only |
| `components/ui/Switch.tsx` | `Switch` | 26 | 0 | Primitive UI | Unused (0 importers), duplicate of `src/shared/ui/Switch.tsx` |
| `components/ui/Tabs.tsx` | `Tabs`, `TabsList`, etc. | 52 | 5 | Primitive UI | Duplicate of `src/shared/ui/Tabs.tsx` |
| `components/ui/Toast.tsx` | None (empty stub) | 3 | 8 | Primitive UI | Broken stub, duplicate of `src/shared/ui/Toast.tsx` |
| `components/ui/Tooltip.tsx` | `Tooltip`, etc. | 25 | 2 | Primitive UI | Duplicate of `src/shared/ui/Tooltip.tsx` |
| `components/ui/WorkerCard.tsx` | `WorkerCard` | 95 | 0 | Primitive UI | Unused (0 importers), duplicate of `src/shared/ui/WorkerCard.tsx` |
| `src/features/auth/components/LoginForm.tsx` | `LoginForm` | 181 | 1 | Domain Form | Client form |
| `src/features/auth/components/RegisterForm.tsx` | `RegisterForm` | 187 | 1 | Domain Form | Client form |
| `src/features/catalog/components/CatalogView.tsx` | `CatalogView` | 897 | 2 | Domain View | Giant component (>250 LOC), monolithic state |
| `src/features/commits/components/CommitEmptyState.tsx` | `CommitEmptyState` | 52 | 2 | Domain View | Unmatched feature |
| `src/features/library/components/SavedTestEmptyState.tsx` | `SavedTestEmptyState` | 52 | 2 | Domain View | Unmatched feature |
| `src/features/projects/components/NewProjectForm.tsx` | `NewProjectForm` | 199 | 2 | Domain Form | Client form |
| `src/features/projects/components/ProjectCard.tsx` | `ProjectCard` | 62 | 2 | Domain UI | Card item |
| `src/features/projects/components/ProjectList.tsx` | `ProjectList` | 96 | 2 | Domain View | Projects ledger |
| `src/features/projects/components/ProjectSettings.tsx` | `ProjectSettings` | 368 | 2 | Domain View | Giant component (>250 LOC), password in state |
| `src/features/reports/components/ReportView.tsx` | `ReportView` | 717 | 2 | Domain View | Giant component (>250 LOC), no markdown sanitize |
| `src/features/results/components/BugDetailView.tsx` | `BugDetailView` | 525 | 2 | Domain View | Giant component (>250 LOC) |
| `src/features/results/components/ResultsView.tsx` | `ResultsView` | 513 | 2 | Domain View | Giant component (>250 LOC) |
| `src/shared/layout/AppShell.tsx` | `AppShell` | 34 | 1 | Layout | Layout wrapper |
| `src/shared/layout/Sidebar.tsx` | `Sidebar` | 202 | 2 | Layout | Main navigation |
| `src/shared/layout/TopBar.tsx` | `TopBar` | 179 | 2 | Layout | Top header bar |
| `src/shared/ui/BudgetMeter.tsx` | `BudgetMeter` | 61 | 1 | Primitive UI | Meter bar |
| `src/shared/ui/Button.tsx` | `Button` | 62 | 20 | Primitive UI | Core button |
| `src/shared/ui/Card.tsx` | `Card`, `CardHeader`, `CardTitle` | 52 | 0 | Primitive UI | Unused (0 importers) |
| `src/shared/ui/Checkbox.tsx` | `Checkbox` | 27 | 3 | Primitive UI | Radix checkbox |
| `src/shared/ui/Chip.tsx` | `Chip` | 90 | 13 | Primitive UI | Badge/chip |
| `src/shared/ui/CodeBlock.tsx` | `CodeBlock` | 111 | 1 | Primitive UI | Pre block |
| `src/shared/ui/ConnectionBadge.tsx` | `ConnectionBadge` | 41 | 0 | Primitive UI | Unused (0 importers) |
| `src/shared/ui/DataTable.tsx` | `DataTable` | 100 | 0 | Primitive UI | Unused (0 importers) |
| `src/shared/ui/Dialog.tsx` | `Dialog`, `DialogContent`, etc. | 102 | 2 | Primitive UI | Radix dialog |
| `src/shared/ui/Drawer.tsx` | `Drawer` | 97 | 2 | Primitive UI | Drawer overlay |
| `src/shared/ui/DropdownMenu.tsx` | `DropdownMenu`, etc. | 55 | 5 | Primitive UI | Radix dropdown |
| `src/shared/ui/EmptyState.tsx` | `EmptyState` | 43 | 9 | Primitive UI | Empty surface |
| `src/shared/ui/FileDropzone.tsx` | `FileDropzone` | 184 | 1 | Primitive UI | Upload dropzone |
| `src/shared/ui/LogViewer.tsx` | `LogViewer` | 176 | 1 | Primitive UI | Terminal log view |
| `src/shared/ui/ReplayPips.tsx` | `ReplayPips` | 112 | 4 | Primitive UI | 3-trial pips |
| `src/shared/ui/RunSwitcher.tsx` | `RunSwitcher` | 108 | 2 | Primitive UI | Active run switcher |
| `src/shared/ui/Skeleton.tsx` | `Skeleton` | 17 | 11 | Primitive UI | Loading pulse |
| `src/shared/ui/Stepper.tsx` | `Stepper` | 90 | 3 | Primitive UI | Pipeline stepper (6 stages only) |
| `src/shared/ui/Switch.tsx` | `Switch` | 26 | 0 | Primitive UI | Unused (0 importers) |
| `src/shared/ui/Tabs.tsx` | `Tabs`, `TabsList`, etc. | 52 | 5 | Primitive UI | Radix tabs |
| `src/shared/ui/Toast.tsx` | `ToastProvider`, `useToast` | 170 | 9 | Primitive UI | Toast context & manager |
| `src/shared/ui/Tooltip.tsx` | `Tooltip`, etc. | 25 | 2 | Primitive UI | Radix tooltip |
| `src/shared/ui/WorkerCard.tsx` | `WorkerCard` | 95 | 0 | Primitive UI | Unused (0 importers) |

### Component Mapping to `design.md` §9
| `design.md` §9 Component | Status | Existing File Path | Missing Capabilities / Deviation |
| :--- | :--- | :--- | :--- |
| `9.1 Button` | **PARTIAL** | `src/shared/ui/Button.tsx` | Lacks oklch primary token, teal export variant, keyboard shortcut hints |
| `9.2 Links` | **PARTIAL** | Native `next/link` | Lacks external icon and underline hover micro-interactions |
| `9.3 Eyebrow pill & tags` | **PARTIAL** | `src/shared/ui/Chip.tsx` | Uses hardcoded hex backgrounds instead of hairline tokens |
| `9.4 Badges` | **PARTIAL** | `src/shared/ui/Chip.tsx` | Lacks dedicated status dot animation and counter pill styling |
| `9.5 Form controls` | **PARTIAL** | Native `<input>`, `<select>` | Scattered across forms; no centralized Input, Label, Textarea primitives |
| `9.6 Cards & stat tiles` | **PARTIAL** | `src/shared/ui/Card.tsx` | Card exists but unused; stat tiles are coded inline inside `page.tsx` |
| `9.7 Tables (hairline ledger)` | **PARTIAL** | `src/shared/ui/DataTable.tsx` | Table component exists but unused; tables in Catalog/Results coded inline |
| `9.8 Tabs` | **EXISTS** | `src/shared/ui/Tabs.tsx` | Uses `@radix-ui/react-tabs` with clean variant switching |
| `9.9 Code Window` | **PARTIAL** | `src/shared/ui/CodeBlock.tsx` | Pre block only; lacks macOS chrome dots, shiki syntax highlighting, copy button |
| `9.10 Terminal (Live)` | **PARTIAL** | `src/shared/ui/LogViewer.tsx` | Lacks auto-scroll pause indicator, ANSI color parser, search filter |
| `9.11 Run Stepper` | **PARTIAL** | `src/shared/ui/Stepper.tsx` | Hardcoded to **6 steps** instead of target **11 stages**; lacks stage metadata |
| `9.12 Run Composer` | **PARTIAL** | `components/features/StartTestForm.tsx` | 623-line monolithic form; not embedded in dashboard canvas |
| `9.13 Verification Timeline` | **PARTIAL** | `src/shared/ui/ReplayPips.tsx` | Renders 3 circular dots; lacks timeline ledger, duration, video links |
| `9.14 Review Gate` | **PARTIAL** | `src/features/catalog/components/CatalogView.tsx` | Embedded inside giant 897 LOC CatalogView; lacks keyboard approve/reject |
| `9.15 Bug Card` | **PARTIAL** | `src/features/results/components/ResultsView.tsx` | Coded inline inside ResultsView rows; no standalone BugCard primitive |
| `9.16 Spec Uploader` | **EXISTS** | `src/shared/ui/FileDropzone.tsx` | Drag-and-drop file upload with preview and size check |
| `9.17 Worker card & budget meter` | **EXISTS** | `src/shared/ui/WorkerCard.tsx`, `BudgetMeter.tsx` | Both exist, but WorkerCard is currently unused (0 importers) |
| `9.18 App Map Graph` | **MISSING** | **NOT FOUND** | No D3 force graph component exists |
| `9.19 Overlays (Drawer/Dialog)` | **EXISTS** | `src/shared/ui/Drawer.tsx`, `Dialog.tsx` | Clean Radix overlays |
| `9.20 Empty / Loading / Error` | **PARTIAL** | `src/shared/ui/EmptyState.tsx`, `Skeleton.tsx` | Empty and skeleton exist; error boundary surface is missing |
| `9.21 Evidence Viewer` | **PARTIAL** | In `BugDetailView.tsx` | Basic image/video tags; lacks trace viewer and network waterfall |
| `9.22 Spec Coverage Matrix` | **MISSING** | **NOT FOUND** | No coverage matrix table mapping spec items to tests |
| `9.23 Command palette & shortcuts` | **MISSING** | **NOT FOUND** | `cmdk` is not installed; no keyboard shortcut dialog |

---

## 5. API LAYER & DATA FLOW

### API Client Architecture
- API calls are made via a centralized typed client: `src/shared/lib/api/client.ts` (duplicated at `lib/api/client.ts`).
- Individual feature API modules exist:
  - `src/features/auth/api.ts` (`authApi`: login, register, getMe, logout)
  - `src/features/projects/api.ts` (`projectsApi`: list, get, create, delete, update)
  - `src/shared/lib/api/hooks.ts` (React Query hooks wrapping `apiClient`)
- In `src/app/debug/connection/page.tsx`, raw `fetch()` and `EventSource` are called directly.

### Backend Endpoints Called in Frontend
| Method + Backend Endpoint | File Path(s):Line | Calling Method | Credentials Included? | Error Handled? | Response Typed? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/health` | `src/shared/lib/api/hooks.ts:16`, `src/app/debug/connection/page.tsx:63` | `apiClient.get` / raw `fetch` | Yes (`include`) | Yes (`ApiError` / `try-catch`) | Typed (`HealthSchema`) |
| `GET /api/v1/config/defaults` | `src/shared/lib/api/hooks.ts:24` | `apiClient.get` | Yes (`include`) | Yes | Typed (`ConfigDefaultsSchema`) |
| `GET /api/v1/stats` | `src/shared/lib/api/hooks.ts:32`, `src/app/debug/connection/page.tsx:77` | `apiClient.get` / raw `fetch` | Yes (`include`) | Yes | Typed (`StatsSchema`) |
| `POST /api/v1/targets/check` | `src/shared/lib/api/hooks.ts:40` | `apiClient.post` | Yes (`include`) | Yes | Typed (`TargetCheckResponseSchema`) |
| `POST /api/v1/specs/upload` | `src/shared/lib/api/hooks.ts:48` | `uploadWithProgress` | Yes (`include`) | Yes | Typed (`SpecUploadResponseSchema`) |
| `GET /api/v1/runs` | `src/shared/lib/api/hooks.ts:68` | `apiClient.get` | Yes (`include`) | Yes | Typed (`RunSchema.array()`) |
| `GET /api/v1/runs/{id}` | `src/shared/lib/api/hooks.ts:79` | `apiClient.get` | Yes (`include`) | Yes | Typed (`RunSchema`) |
| `POST /api/v1/runs` | `src/shared/lib/api/hooks.ts:89` | `apiClient.post` | Yes (`include`) | Yes | Typed (`RunSchema`) |
| `POST /api/v1/runs/{id}/start` | `src/shared/lib/api/hooks.ts:100` | `apiClient.post` | Yes (`include`) | Yes | Typed (`RunSchema`) |
| `POST /api/v1/runs/{id}/cancel` | `src/shared/lib/api/hooks.ts:111` | `apiClient.post` | Yes (`include`) | Yes | Untyped (`unknown`) |
| `POST /api/v1/runs/{id}/retry` | `src/shared/lib/api/hooks.ts:122` | `apiClient.post` | Yes (`include`) | Yes | Typed (`RunSchema`) |
| `POST /api/v1/runs/{id}/resume` | `src/shared/lib/api/hooks.ts:133` | `apiClient.post` | Yes (`include`) | Yes | Untyped (`unknown`) |
| `GET /api/v1/runs/{id}/catalog` | `src/shared/lib/api/hooks.ts:144` | `apiClient.get` | Yes (`include`) | Yes | Typed (`CatalogTestSchema.array()`) |
| `POST /api/v1/runs/{id}/review` | `src/shared/lib/api/hooks.ts:155` | `apiClient.post` | Yes (`include`) | Yes | Untyped (`unknown`) |
| `GET /api/v1/runs/{id}/review-log` | `src/shared/lib/api/hooks.ts:166` | `apiClient.get` | Yes (`include`) | Yes | Typed (`ReviewDecisionSchema.array()`) |
| `GET /api/v1/runs/{id}/execution` | `src/shared/lib/api/hooks.ts:177` | `apiClient.get` | Yes (`include`) | Yes | Typed (`ExecutionStateSchema`) |
| `GET /api/v1/runs/{id}/tests` | `src/shared/lib/api/hooks.ts:188` | `apiClient.get` | Yes (`include`) | Yes | Typed (`ExecutionTestSchema.array()`) |
| `GET /api/v1/runs/{id}/bugs` | `src/shared/lib/api/hooks.ts:199` | `apiClient.get` | Yes (`include`) | Yes | Typed (`BugSchema.array()`) |
| `GET /api/v1/bugs/{bugId}` | `src/shared/lib/api/hooks.ts:210` | `apiClient.get` | Yes (`include`) | Yes | Typed (`BugSchema`) |
| `GET /api/v1/runs/{id}/report` | `src/shared/lib/api/hooks.ts:221` | `apiClient.get` | Yes (`include`) | Yes | Typed (`ReportSchema`) |
| `GET /api/v1/runs/{id}/logs` | `src/shared/hooks/useRunStream.ts:51` | raw `fetch` | Yes (`include`) | Yes | Untyped array |
| `GET /api/v1/runs/{id}/stream` | `src/shared/hooks/useRunStream.ts:175` | native `EventSource` | Default (Same-origin) | Reconnect loop | Typed via Zod parse |
| `POST /api/v1/auth/login` | `src/features/auth/api.ts:25` | `apiClient.post` | Yes (`include`) | Yes | Typed |
| `POST /api/v1/auth/register` | `src/features/auth/api.ts:33` | `apiClient.post` | Yes (`include`) | Yes | Typed |
| `GET /api/v1/auth/me` | `src/features/auth/api.ts:41`, `src/app/debug/connection/page.tsx:91` | `apiClient.get` / raw `fetch` | Yes (`include`) | Yes | Typed |
| `POST /api/v1/auth/logout` | `src/features/auth/api.ts:45` | `apiClient.post` | Yes (`include`) | Yes | Typed |
| `GET /api/v1/projects` | `src/features/projects/api.ts:34` | `apiClient.get` | Yes (`include`) | Yes | Typed |
| `GET /api/v1/projects/{id}` | `src/features/projects/api.ts:38` | `apiClient.get` | Yes (`include`) | Yes | Typed |
| `POST /api/v1/projects` | `src/features/projects/api.ts:42` | `apiClient.post` | Yes (`include`) | Yes | Typed |
| `DELETE /api/v1/projects/{id}` | `src/features/projects/api.ts:46` | `apiClient.delete` | Yes (`include`) | Yes | Untyped |
| `PUT /api/v1/projects/{id}` | `src/features/projects/api.ts:50` | `apiClient.put` | Yes (`include`) | Yes | Typed |
| `GET /api/v1/projects/{id}/credentials` | `src/features/projects/components/ProjectSettings.tsx:98` | `apiClient.get` | Yes (`include`) | Yes | Untyped |
| `PUT /api/v1/projects/{id}/credentials` | `src/features/projects/components/ProjectSettings.tsx:128` | `apiClient.put` | Yes (`include`) | Yes | Untyped |

### Comparison with `design.md` §11.2 Matrix
- **Endpoints in `design.md` never called in current frontend:**
  - `GET /runs/{id}/metrics` (Metrics fetched as part of report instead of standalone)
  - `GET /runs/{id}/export` (Full zip export endpoint)
  - `GET /runs/{id}/export/scripts` (Playwright script zip export)
  - `GET /runs/{id}/report/export` (Markdown executive report export)
  - `GET /runs/{id}/tests/export?format=csv|json` (Test catalog export)
  - `GET /runs/{id}/app-map` (Sitemap & discovery graph endpoint)
  - `DELETE /runs/{id}` (Run deletion endpoint)
- **Legacy un-prefixed routes check:**
  No un-prefixed `/runs`, `/health`, or `/config` calls are made directly to the backend. All calls use `/api/v1/*`.

### Authentication Handling
- **Mechanism:** HttpOnly cookie-based session via `credentials: "include"`.
- **401 Handling:** In `apiClient`: if `res.status === 401`, redirects via `window.location.href = /login?returnUrl=...`.
- **CRITICAL BUG IN MIDDLEWARE:** `apps/web/middleware.ts` checks:
  ```ts
  const sessionCookie =
    request.cookies.get("session") ||
    request.cookies.get("access_token") ||
    request.cookies.get("auth_token") ||
    request.cookies.get("token") ||
    request.cookies.get("kawach_session");
  ```
  The backend sets cookie `session_id`. Because `session_id` is missing from `middleware.ts`, authenticated users are redirected in an infinite redirect loop to `/login`.

### Real-time SSE & Streaming Protocol
- **SSE Client File:** `src/shared/hooks/useRunStream.ts` (384 LOC).
- **Endpoint:** `/api/v1/runs/${runId}/stream`.
- **Event Types Handled:**
  - `run.status`: Updates run status & progress in React Query cache.
  - `log`: Appends to last 500 log entries.
  - `catalog.ready`: Injects catalog tests into cache.
  - `review.decision`: Updates test review status and review log.
  - `worker.update`: Updates execution state workers.
  - `test.update`: Updates execution state tests.
  - `bug.suspected`, `bug.verification`, `bug.final`: Updates bug verification replays and results.
  - `budget.update`: Updates budget consumption.
  - `run.done`: Invalidates query cache and disconnects.
- **Missing Event Types (vs `design.md` §5 & §13):**
  - `stage`: Target event for pipeline stage transitions (`run.status` used instead).
  - `test.status`: Target event for individual test execution updates (`test.update` used instead).
  - `worker.status`: Target event for worker lifecycle (`worker.update` used instead).
  - `ping`: Keepalive event is unhandled.
- **Fallback / Polling Mechanism:**
  When `failureCountRef.current >= 3`, falls back to `startPolling()` querying `/api/v1/runs/${runId}` every 3000ms.

### Normalization Layer & TypeScript Shapes
- **Status:** **PARTIAL / AD-HOC**.
- `types/index.ts` accepts dual snake_case / camelCase formats via Zod `.transform()` or `.optional()`, but there is NO dedicated normalization layer in `features/*/schemas.ts` as specified in `design.md` §11.1.
- Mismatches:
  - `bug.steps_to_reproduce` is snake_case; bug cards expect `stepsToReproduce`.
  - `target_url` vs `targetUrl` is handled inconsistently across forms and cards.

---

## 6. STYLING & DESIGN-TOKEN STATE

### Global CSS Inspection (`src/app/globals.css`)
```css
@import url('https://fonts.googleapis.com/css2?family=Cookie&family=Grand+Hotel&family=Oleo+Script&display=swap');
@import "tailwindcss";

@theme {
  --color-ivory: #FAF9F5;
  --color-cloud: #F0EEE6;
  --color-cloud-hover: #E9E6DC;
  --color-card-border: #E3DACC;
  
  --color-clay: #D97757;
  --color-clay-hover: #C15F3C;
  --color-clay-subtle: #F6EDE8;
  --color-clay-focus: rgba(217, 119, 87, 0.25);
  
  --color-text-primary: #141413;
  --color-text-secondary: #6B6A64;
  --color-text-tertiary: #8A887F;

  --color-status-confirmed: #5E8C61;
  --color-status-confirmed-bg: #EBF2EB;
  
  --color-status-flaky: #D4A02A;
  --color-status-flaky-bg: #FBF4E6;
  
  --color-status-failed: #C4473A;
  --color-status-failed-bg: #FAEBE9;
  
  --color-status-neutral: #8A887F;
  --color-status-neutral-bg: #F2F1EE;

  --font-serif: var(--font-newsreader), Georgia, serif;
  --font-sans: var(--font-inter), -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: var(--font-jetbrains-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

:root {
  --bg-page: #FAF9F5;
  --bg-sidebar: #F0EEE6;
  --border-card: #E3DACC;
  --color-clay: #D97757;
  --color-clay-hover: #C15F3C;
}

html, body {
  background-color: #FAF9F5;
  color: #141413;
  font-family: var(--font-inter), -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #D9D4C7;
  border-radius: 9999px;
}
::-webkit-scrollbar-thumb:hover {
  background: #C4BEAF;
}

:focus-visible {
  outline: 2px solid #D97757;
  outline-offset: 2px;
}

.card-base {
  background-color: #FFFFFF;
  border: 1px solid #E3DACC;
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(20, 20, 19, 0.05);
}

.font-heading {
  font-family: var(--font-newsreader), Georgia, serif;
}
```

### Design Token Conformance vs `design.md` Appendix A
- **OKLCH Color Tokens (`--primary: oklch(...)`):** **ENTIRELY MISSING**.
- **Missing Token Groups:**
  - Canvas & panel tokens: `--canvas`, `--panel`, `--panel-muted`, `--hairline`, `--hairline-strong` are all missing.
  - Status tokens: `--status-queued`, `--status-running`, `--status-passed`, `--status-failed`, `--status-flaky`, `--status-reproduced` (oklch) are missing.
  - Log & syntax tokens: `--log-bg`, `--log-fg`, `--syntax-*` are missing.
- **Typography & Fonts:**
  - Google cursive fonts (`Cookie`, `Grand Hotel`, `Oleo Script`) imported via `@import url(...)` in `globals.css`.
  - Next.js Google Fonts loaded in `layout.tsx`: `Newsreader`, `Inter`, `JetBrains_Mono`.
  - `Geist` and `Geist Mono` required by `design.md` §3 are NOT loaded.
- **Dark Mode:**
  - **NOT IMPLEMENTED** (No `.dark` class block, no CSS media query, no theme toggle).

### Codebase Styling Violations
- **Hard-coded Hex & RGB/HSL Colors:** **1,592 occurrences**
- **Inline `style={{...}}` Usage:** **19 occurrences**
- **Arbitrary Tailwind Values (`bg-[#...]`, `text-[11px]`):** **1,770 occurrences**
- **Default Tailwind Palette Classes (`border-stone-200`):** **30 occurrences**
- **Multiple CSS Files:** 1 file (`src/app/globals.css`).

#### Top 20 Hard-Coded Hex Examples
1. `components/features/StartTestForm.tsx:242`: `border-[#E3DACC]`
2. `components/features/StartTestForm.tsx:248`: `text-[#141413]`
3. `components/features/StartTestForm.tsx:251`: `text-[#8A887F]`
4. `components/features/StartTestForm.tsx:270`: `bg-[#FAF9F5] border-[#E3DACC] text-[#141413] focus:ring-[#D97757]`
5. `components/layout/Sidebar.tsx:92`: `bg-[#F5F4ED]`
6. `components/layout/Sidebar.tsx:101`: `text-[#141413]`
7. `components/layout/TopBar.tsx:101`: `bg-[#FAF9F5]/90`
8. `src/shared/ui/Button.tsx:24`: `bg-[#D97757] hover:bg-[#C15F3C]`
9. `src/shared/ui/Chip.tsx:32`: `bg-[#EBF2EB] text-[#5E8C61]`
10. `src/features/catalog/components/CatalogView.tsx:184`: `border-[#E3DACC] bg-[#FAF9F5]`
11. `src/features/results/components/ResultsView.tsx:142`: `text-[#141413] border-[#E3DACC]`
12. `src/features/results/components/BugDetailView.tsx:112`: `bg-[#FAEBE9] border-[#C4473A]`
13. `src/features/reports/components/ReportView.tsx:88`: `text-[#141413] bg-[#FAF9F5]`
14. `src/app/page.tsx:210`: `bg-[#FAF9F5] text-[#141413] border-[#E3DACC]`
15. `src/app/page.tsx:340`: `text-[#8A887F]`
16. `src/features/projects/components/ProjectList.tsx:68`: `bg-[#FAF9F5] border-[#E3DACC]`
17. `src/features/projects/components/ProjectSettings.tsx:140`: `bg-white border-[#E3DACC]`
18. `src/features/auth/components/LoginForm.tsx:95`: `bg-[#FAF9F5] text-[#141413] border-[#E3DACC]`
19. `src/shared/ui/LogViewer.tsx:78`: `bg-[#141413] text-[#FAF9F5]`
20. `src/shared/ui/DataTable.tsx:42`: `border-[#E3DACC] hover:bg-[#FAF9F5]`

#### Top Inline `style={{...}}` Usages
1. `components/layout/Sidebar.tsx:101`: `style={{ fontFamily: "'Billabong', 'Cookie', 'Grand Hotel', 'Brush Script MT', cursive" }}`
2. `src/shared/layout/Sidebar.tsx:101`: `style={{ fontFamily: "'Billabong', 'Cookie', 'Grand Hotel', 'Brush Script MT', cursive" }}`
3. `components/layout/Sidebar.tsx:109`: `style={{ scrollbarWidth: "thin" }}`
4. `src/shared/layout/Sidebar.tsx:109`: `style={{ scrollbarWidth: "thin" }}`
5. `components/ui/BudgetMeter.tsx:56`: `style={{ width: `${percentage}%` }}`
6. `src/shared/ui/BudgetMeter.tsx:56`: `style={{ width: `${percentage}%` }}`
7. `components/ui/FileDropzone.tsx:168`: `style={{ width: `${uploadProgress}%` }}`
8. `src/shared/ui/FileDropzone.tsx:168`: `style={{ width: `${uploadProgress}%` }}`
9. `components/ui/LogViewer.tsx:128`: `style={{ maxHeight }}`
10. `src/shared/ui/LogViewer.tsx:128`: `style={{ maxHeight }}`

### Aesthetic Assessment
The current UI does NOT follow the Momentic design blueprint from `design.md`. Instead of a high-density, calm technical workstation featuring hairline borders, tight mono metadata, and precision oklch tokens, it presents an ad-hoc "warm clay and ivory" editorial blog aesthetic. The logo brand uses an informal handwritten script font (`Cookie`/`Grand Hotel`), borders are chunky `#E3DACC` cards, buttons use terracotta clay `#D97757`, dark mode is completely absent, and nearly 1,800 arbitrary hex classes override any cohesive design system.

---

## 7. STATE, HOOKS & UTILITIES

### Modules & Stores
| Path | Exports | Purpose & Shape |
| :--- | :--- | :--- |
| `src/shared/lib/store/uiStore.ts` | `useUiStore` | Zustand store: `{ activeRunId: string | null, sidebarCollapsed: boolean, setActiveRunId, toggleSidebar }` |
| `src/shared/hooks/useRunStream.ts` | `useRunStream` | SSE stream consumer for `/runs/${id}/stream` with React Query cache mutators & 3s polling fallback |
| `src/shared/lib/api/hooks.ts` | 14 Query/Mutation hooks | React Query wrappers for health, config, stats, runs, catalog, bugs, reports, and review |
| `src/shared/ui/Toast.tsx` | `ToastProvider`, `useToast` | React Context toast notification system (success, error, info) |
| `src/shared/lib/utils.ts` | `cn`, `formatDate`, `formatDuration`, `formatCost`, `getStatusColor` | Class merging, duration math, and badge color mappers |
| `src/shared/lib/mocks/devMockService.ts` | `devMockService` | 620-line in-memory mock backend simulator |

### Duplicate Helper Functions
- Status colors are computed in `src/shared/lib/utils.ts` (`getStatusColor`), `src/shared/ui/Chip.tsx` (`statusColorMap`), and `src/shared/ui/Stepper.tsx` (`stepStyles`).
- Date & time formatting is repeated across `ReportView.tsx`, `BugDetailView.tsx`, and `utils.ts`.

---

## 8. FEATURE CHECKLIST

| Feature Requirement (`design.md` & PRD) | Status | File Path | Deficiencies |
| :--- | :--- | :--- | :--- |
| Run stages stepper (11 stages) | **PARTIAL** | `src/shared/ui/Stepper.tsx` | Only implements 6 stages; missing 11-stage pipeline |
| Review Gate banner + Approve/Reject/Resume | **DONE** | `src/features/catalog/components/CatalogView.tsx` | Works, but buried in 897-line view |
| Add custom test & Edit test | **DONE** | `src/features/catalog/components/CatalogView.tsx` | Dialog and drawer forms functional |
| Review log | **DONE** | `src/features/catalog/components/CatalogView.tsx` | Autonomous & human review log tab |
| Live terminal with auto-scroll pause | **PARTIAL** | `src/shared/ui/LogViewer.tsx` | Level filters work; auto-scroll pause indicator is missing |
| Worker cards & active tasks | **DONE** | `src/shared/ui/WorkerCard.tsx` | Component complete, but currently unused (0 importers) |
| Budget meters (pages, time, steps, cost) | **DONE** | `src/shared/ui/BudgetMeter.tsx` | Visual progress bars work |
| Bug list with Confirmed/Flaky filters | **DONE** | `src/features/results/components/ResultsView.tsx` | Filter chips functional |
| Bug detail with 3-trial Verification Timeline | **PARTIAL** | `src/features/results/components/BugDetailView.tsx` | Shows 3-trial pips; lacks timeline ledger & video link sync |
| Evidence viewer (screenshot/video/trace) | **PARTIAL** | `src/features/results/components/BugDetailView.tsx` | Basic tabs; lacks network waterfall & integrated trace viewer |
| Playwright script viewer | **PARTIAL** | `src/features/results/components/BugDetailView.tsx` | Uses raw `<pre>`; lacks syntax highlighting and copy button |
| App map visualization (D3 graph) | **MISSING** | **NOT FOUND** | Entire feature missing; `/runs/[id]/sitemap` does not exist |
| Report page with metrics + Markdown + 4 exports | **PARTIAL** | `src/features/reports/components/ReportView.tsx` | Metrics & exports work; markdown lacks `rehype-sanitize` |
| Projects CRUD | **DONE** | `src/features/projects/` | List, create, delete, and edit functional |
| Credentials panel (zero-secret) | **PARTIAL** | `src/features/projects/components/ProjectSettings.tsx` | Plaintext input used; lacks "Password Stored (Encrypted)" badge |
| Target URL pre-flight validation | **DONE** | `components/features/StartTestForm.tsx` | Debounced `/api/v1/targets/check` check |
| Spec upload (preview + item counts) | **DONE** | `src/shared/ui/FileDropzone.tsx` | Drag-and-drop file uploader works |
| Config/defaults-driven budget limits | **DONE** | `components/features/StartTestForm.tsx` | Populated via `/api/v1/config/defaults` |
| Dashboard stats tiles (`/stats`) | **DONE** | `src/app/page.tsx` | Top KPI summary cards rendered |
| Health indicator (`/health`) | **DONE** | `src/shared/layout/TopBar.tsx` | Header badge shows live/offline status |
| Auth pages (login, register) | **DONE** | `src/app/(auth)/login/`, `register/` | Full form flows exist |
| Guest mode | **MISSING** | `apps/web/middleware.ts` | 401 forces immediate redirect to login; guest exploration blocked |
| Command palette (`cmdk`) | **MISSING** | **NOT FOUND** | Missing package and component |
| Dark mode toggle | **MISSING** | **NOT FOUND** | Missing theme state, CSS tokens, and toggle |
| Security: `dangerouslySetInnerHTML` | **SAFE** | None found | 0 instances in codebase |
| Security: Content sanitization | **PARTIAL** | `src/features/reports/components/ReportView.tsx` | Unsanitized text output in report body |
| Security: Password in state / storage | **PARTIAL** | `src/features/projects/components/ProjectSettings.tsx` | Password held in React component state string |

---

## 9. PROBLEM LIST

### Severity: Blocker
1. **Broken Imports Causing Compilation Failure**
   - File: `src/app/execution/[runId]/page.tsx:3`
   - Issue: `import { ExecutionCockpit } from "@/features/runs/components/ExecutionCockpit";` targets non-existent module.
   - Fix: Implement `ExecutionCockpit` under `src/features/runs/components/ExecutionCockpit.tsx` or route to `src/features/results/components/ResultsView.tsx`.
2. **Broken Import in Project Creation Wizard**
   - File: `src/app/(app)/projects/new/page.tsx:5`
   - Issue: `import { StartTestForm } from "@/features/runs/components/StartTestForm";` points to wrong location (`components/features/StartTestForm.tsx`).
   - Fix: Correct import path to `@/components/features/StartTestForm` or move file to `src/features/runs/components/`.
3. **Session Cookie Mismatch in Middleware (Infinite Redirect Loop)**
   - File: `apps/web/middleware.ts:24-29`
   - Issue: Middleware checks for `session`, `access_token`, `auth_token`, `token`, `kawach_session`, but backend issues `session_id`. All logged-in users are blocked and redirected to `/login`.
   - Fix: Add `request.cookies.get("session_id")` to `sessionCookie` check.

### Severity: High
4. **Massive Code Duplication (~4,500 Redundant LOC)**
   - Files: `components/*` vs `src/shared/*`, `lib/*` vs `src/shared/lib/*`, `hooks/*` vs `src/shared/hooks/*`.
   - Issue: 27 component files and all API/mock/store/hook files are duplicated between root and `src/shared/`.
   - Fix: Delete root `components/`, `hooks/`, and `lib/` folders; standardize all imports on `src/`.
5. **Missing OKLCH Color Tokens & Design System**
   - File: `src/app/globals.css`
   - Issue: Zero tokens from `design.md` Appendix A exist. The app relies on 1,592 hardcoded hex values and 1,770 arbitrary Tailwind utility overrides.
   - Fix: Replace `globals.css` with `design.md` Appendix A and refactor classes to design tokens (`bg-primary`, `border-hairline`, etc.).
6. **Giant Monolithic View Components (>500 LOC)**
   - Files: `CatalogView.tsx` (897 LOC), `src/app/page.tsx` (754 LOC), `ReportView.tsx` (717 LOC), `StartTestForm.tsx` (623 LOC), `BugDetailView.tsx` (525 LOC), `ResultsView.tsx` (513 LOC).
   - Issue: Excessive component complexity violating the 250 LOC rule from `design.md` §14.1.
   - Fix: Break views into sub-components (`CatalogTable`, `TestDrawer`, `ReviewActionBar`, `MetricKpis`).
7. **Missing Core Design System Pages**
   - Files: `/runs/[id]/sitemap` (App Map), `/runs/[id]/timeline` (Timeline), `/settings` (Settings).
   - Issue: Core pages specified in `design.md` §10 are completely absent.
   - Fix: Create missing App Router routes.

### Severity: Medium
8. **Missing Error Boundaries & Loading States**
   - Files: `apps/web/src/app/**`
   - Issue: Zero `loading.tsx`, `error.tsx`, `global-error.tsx`, or `not-found.tsx` files exist. Runtime API errors crash the entire client React tree.
   - Fix: Add root and nested `error.tsx`, `loading.tsx`, and `not-found.tsx` boundaries.
9. **Informal Handwritten Script Fonts**
   - Files: `src/app/globals.css:1`, `src/shared/layout/Sidebar.tsx:101`
   - Issue: Imports Google Fonts `Cookie`, `Grand Hotel`, `Oleo Script` and sets `fontFamily: "Billabong, Cookie..."` for the sidebar logo.
   - Fix: Remove script font imports; adopt `Geist`, `Geist Mono`, and `JetBrains Mono` per `design.md` §3.
10. **Unused / Dead Components (0 Importers)**
    - Files: `DataTable.tsx`, `Card.tsx`, `WorkerCard.tsx`, `Switch.tsx`, `ConnectionBadge.tsx`.
    - Issue: Core UI components were authored but never wired into pages (inline elements used instead).
    - Fix: Refactor pages to consume these shared components.
11. **Missing Production Dependencies**
    - File: `apps/web/package.json`
    - Issue: `recharts`, `react-markdown`, `rehype-sanitize`, `cmdk`, `sonner`, `d3-force` are required by specs but not installed.
    - Fix: Install missing packages via `npm install` / `pnpm add`.

### Severity: Low
12. **Console Warnings in API Client**
    - File: `src/shared/lib/api/client.ts:153, 219`
    - Issue: `console.warn` left in schema error fallbacks.
    - Fix: Replace with structured telemetry/logger.
13. **Any Types Usage**
    - Files: `src/app/debug/connection/page.tsx`, `LoginForm.tsx`, `RegisterForm.tsx`
    - Issue: 10 explicit `: any` or `as any` casts found.
    - Fix: Replace with strict typed error handling (`err instanceof Error`).

---

## 10. KEY FILES — VERBATIM

### `apps/web/package.json`
```json
{
  "name": "kawach",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",
    "types": "openapi-typescript ../../packages/contracts/openapi.json -o src/generated/api-types.ts"
  },

  "dependencies": {
    "@hookform/resolvers": "^5.9.2",
    "@radix-ui/react-checkbox": "^1.4.1",
    "@radix-ui/react-dialog": "^1.3.1",
    "@radix-ui/react-dropdown-menu": "^2.2.1",
    "@radix-ui/react-switch": "^1.4.1",
    "@radix-ui/react-tabs": "^1.2.1",
    "@radix-ui/react-tooltip": "^1.4.1",
    "@tanstack/react-query": "^5.104.4",
    "clsx": "^2.1.1",
    "lucide-react": "^1.59.0",
    "next": "16.4.2",
    "react": "19.3.0",
    "react-dom": "19.3.0",
    "react-hook-form": "^7.90.0",
    "tailwind-merge": "^3.7.0",
    "zod": "^4.6.7",
    "zustand": "^5.0.15"
  },
  "devDependencies": {
    "@tailwindcss/turbopack": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.4.2",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}

```

### `apps/web/next.config.ts`
```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

```

### `apps/web/tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*", "./*"]
    }
  },

  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts",
    ".next/dev/types/**/*.ts",
    "**/*.mts"
  ],
  "exclude": ["node_modules", "contracts", "runner", "target-app"]
}

```

### Tailwind Config
`NOT FOUND` (Tailwind v4 is configured via inline `@theme` in `apps/web/src/app/globals.css`).

### PostCSS Config
`NOT FOUND`

### `components.json` (shadcn)
`NOT FOUND`

### `apps/web/src/app/layout.tsx` (Root Layout)
```tsx
import type { Metadata } from "next";
import { Newsreader, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/components/providers/QueryProvider";
import { AppShell } from "@/components/layout/AppShell";

const newsreader = Newsreader({
  subsets: ["latin"],
  variable: "--font-newsreader",
  display: "swap",
  style: ["normal", "italic"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "KAWACH | Autonomous AI QA Prover",
  description:
    "Production-grade AI QA testing agent that doesn't just report bugs, it proves them with deterministic replays.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans bg-[#FAF9F5] text-[#141413]">
        <AppProviders>
          <AppShell>{children}</AppShell>
        </AppProviders>
      </body>
    </html>
  );
}

```

### `apps/web/src/shared/lib/api/client.ts` (API Client - First 150 & Last 50 Lines)
```typescript
import { z } from "zod";

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly requestId?: string;
  public readonly details?: unknown;

  constructor(params: {
    message: string;
    code?: string;
    status: number;
    requestId?: string;
    details?: unknown;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code || `HTTP_${params.status}`;
    this.status = params.status;
    this.requestId = params.requestId;
    this.details = params.details;
  }
}

interface RequestOptions<TResponse> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  schema?: z.ZodType<TResponse>;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function apiClient<TResponse = unknown>(
  endpoint: string,
  options: RequestOptions<TResponse> = {}
): Promise<TResponse> {
  const {
    method = "GET",
    body,
    headers = {},
    schema,
    timeoutMs = 30000,
    signal: userSignal,
  } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Link user signal if provided
  if (userSignal) {
    userSignal.addEventListener("abort", () => controller.abort());
  }

  const reqHeaders: Record<string, string> = {
    Accept: "application/json",
    ...headers,
  };

  let serializedBody: BodyInit | undefined;
  if (body !== undefined) {
    if (body instanceof FormData) {
      serializedBody = body;
      // Let browser set multipart boundary
      delete reqHeaders["Content-Type"];
    } else {
      reqHeaders["Content-Type"] = "application/json";
      serializedBody = JSON.stringify(body);
    }
  }

  try {
    const res = await fetch(endpoint, {
      method,
      headers: reqHeaders,
      body: serializedBody,
      signal: controller.signal,
      credentials: "include", // send httpOnly cookies
    });

    clearTimeout(timeoutId);

    // Handle 401 Unauthorized
    if (res.status === 401) {
      if (typeof window !== "undefined") {
        const currentPath = window.location.pathname;
        if (!currentPath.startsWith("/login")) {
          const returnUrl = encodeURIComponent(
            window.location.pathname + window.location.search
          );
          window.location.href = `/login?returnUrl=${returnUrl}`;
        }
      }
      throw new ApiError({
        message: "Session expired or unauthorized. Please log in.",
        code: "UNAUTHORIZED",
        status: 401,
      });
    }

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    let responseData: unknown = null;
    if (isJson) {
      try {
        responseData = await res.json();
      } catch {
        responseData = null;
      }
    } else if (res.status !== 204) {
      responseData = await res.text();
    }

    if (!res.ok) {
      const errObj =
        typeof responseData === "object" && responseData !== null
          ? (responseData as Record<string, unknown>)
          : {};

      const envelope =
        typeof errObj.error === "object" && errObj.error !== null
          ? (errObj.error as Record<string, unknown>)
          : errObj;

      const message =
        (typeof envelope.message === "string" && envelope.message) ||
        (typeof errObj.detail === "string" && errObj.detail) ||
        res.statusText ||
        "Request failed";

      const code =
        (typeof envelope.code === "string" && envelope.code) ||
        (typeof errObj.code === "string" && errObj.code) ||
        `HTTP_${res.status}`;

      const requestId =
        (typeof envelope.requestId === "string" && envelope.requestId) ||
        (typeof errObj.request_id === "string" && errObj.request_id) ||
        res.headers.get("x-request-id") ||
        undefined;

      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("kawach:api-error", {
            detail: {
              status: res.status,
              url: endpoint,
              code,
              requestId,

// ... [OMITTED 121 LINES (Total: 321 LOC)] ...

          status,
          details: parsed,
        })
      );
    };

    xhr.onerror = () => {
      reject(
        new ApiError({
          message: "Network error during upload",
          code: "NETWORK_ERROR",
          status: 0,
        })
      );
    };

    xhr.send(formData);
  });
}

apiClient.get = <TResponse = unknown>(
  endpoint: string,
  options?: Omit<RequestOptions<TResponse>, "method">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "GET" });
};

apiClient.post = <TResponse = unknown>(
  endpoint: string,
  body?: unknown,
  options?: Omit<RequestOptions<TResponse>, "method" | "body">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "POST", body });
};

apiClient.put = <TResponse = unknown>(
  endpoint: string,
  body?: unknown,
  options?: Omit<RequestOptions<TResponse>, "method" | "body">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "PUT", body });
};

apiClient.delete = <TResponse = unknown>(
  endpoint: string,
  options?: Omit<RequestOptions<TResponse>, "method">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "DELETE" });
};

```

### `apps/web/src/shared/hooks/useRunStream.ts` (SSE Hook - First 150 & Last 50 Lines)
```typescript
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  type Run,
  type SSEEvent,
  SSEEventSchema,
  type CatalogTest,
  type ReviewDecision,
  type Bug,
  type ExecutionTest,
  type ExecutionState,
  type Worker,
} from "@/types";
import { API_ENDPOINTS } from "@/lib/api/config";
import { apiClient } from "@/lib/api/client";

export type ConnectionState = "live" | "reconnecting" | "polling" | "disconnected";

export interface StreamLogEntry {
  id: string;
  timestamp: string;
  level: "info" | "warn" | "error" | "debug";
  source?: string;
  message: string;
}

export function useRunStream(runId: string | null | undefined, isFinished = false) {
  const queryClient = useQueryClient();
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [logs, setLogs] = useState<StreamLogEntry[]>([]);

  const eventSourceRef = useRef<EventSource | null>(null);
  const failureCountRef = useRef(0);
  const lastEventIdRef = useRef<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Initial load of pipeline logs from backend (works even if run has completed/failed)
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    fetch(`/api/v1/runs/${runId}/logs`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load logs");
        return res.json();
      })
      .then((data: StreamLogEntry[]) => {
        if (!cancelled && Array.isArray(data) && data.length > 0) {
          setLogs((prev) => {
            const seen = new Set(data.map((l) => `${l.timestamp}-${l.message}`));
            const extra = prev.filter((l) => !seen.has(`${l.timestamp}-${l.message}`));
            return [...data, ...extra].slice(-500);
          });
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Helper to handle received SSE events and update React Query cache directly
  const handleSSEMessage = useCallback(
    (rawEventData: string, eventId?: string) => {
      if (eventId) {
        lastEventIdRef.current = eventId;
      }

      let parsedJson: unknown;
      try {
        parsedJson = JSON.parse(rawEventData);
      } catch {
        // Not JSON, ignore safely
        return;
      }

      const parseResult = SSEEventSchema.safeParse(parsedJson);
      if (!parseResult.success) {
        // Unknown or invalid event type, ignore safely
        return;
      }

      const event: SSEEvent = parseResult.data;

      if (!runId) return;

      switch (event.type) {
        case "run.status": {
          queryClient.setQueryData<Run>(["runs", runId], (old) => {
            if (!old) return old;
            return {
              ...old,
              status: event.status,
              progress: event.progress,
            };
          });
          queryClient.invalidateQueries({ queryKey: ["runs", runId] });
          break;
        }

        case "log": {
          const newEntry: StreamLogEntry = {
            id: `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
            timestamp: event.timestamp || new Date().toISOString(),
            level: event.level,
            source: event.source,
            message: event.message,
          };
          setLogs((prev) => [...prev.slice(-499), newEntry]); // keep last 500 lines
          break;
        }

        case "catalog.ready": {
          queryClient.setQueryData<CatalogTest[]>(
            ["runs", runId, "catalog"],
            event.tests
          );
          break;
        }

        case "review.decision": {
          const decision = event.decision;
          queryClient.setQueryData<CatalogTest[]>(
            ["runs", runId, "catalog"],
            (old: CatalogTest[] | undefined) => {
              if (!old) return old;
              return old.map((test) =>
                test.id === decision.test_id
                  ? {
                      ...test,
                      review_status: decision.decision,
                      last_decision: decision,
                    }
                  : test
              );
            }
          );
          queryClient.setQueryData<ReviewDecision[]>(
            ["runs", runId, "reviewLog"],
            (old: ReviewDecision[] | undefined) => (old ? [decision, ...old] : [decision])
          );
          break;
        }

        case "worker.update": {
          const worker = event.worker;

// ... [OMITTED 184 LINES (Total: 384 LOC)] ...

  useEffect(() => {
    connectSSERef.current = connectSSE;
  }, [connectSSE]);

  useEffect(() => {
    if (!runId || isFinished) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      return;
    }

    connectSSERef.current();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [runId, isFinished]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return {
    connectionState,
    logs,
    clearLogs,
    isLive: connectionState === "live",
    isPolling: connectionState === "polling",
    isReconnecting: connectionState === "reconnecting",
  };
}
```

### `apps/web/types/index.ts` (Main Types File - First 150 & Last 50 Lines)
```typescript
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
export const TestStatusSchema = z.enum([
  "queued",
  "running",
  "passed",
  "failed",
  "skipped",
  "error", // Infrastructure failure, never counted as a bug
]);
export type TestStatus = z.infer<typeof TestStatusSchema>;

export const ExecutionTestSchema = z.object({
  id: z.string(),

// ... [OMITTED 298 LINES (Total: 498 LOC)] ...

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
```

### `apps/web/src/app/page.tsx` (Dashboard / Home - First 150 & Last 50 Lines)
```tsx
"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useRuns,
  useRun,
  useStats,
  useCatalog,
  useSubmitReview,
  useBugs,
} from "@/lib/api/hooks";
import { useRunStream } from "@/hooks/useRunStream";
import { useUiStore } from "@/lib/store/uiStore";
import { StartTestForm } from "@/components/features/StartTestForm";
import { Stepper } from "@/components/ui/Stepper";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { LogViewer } from "@/components/ui/LogViewer";
import { ReplayPips } from "@/components/ui/ReplayPips";
import { BudgetMeter } from "@/components/ui/BudgetMeter";
import { Checkbox } from "@/components/ui/Checkbox";
import { useToast } from "@/components/ui/Toast";
import {
  extractHostname,
  formatRelativeTime,
  formatDateTime,
} from "@/lib/utils";
import {
  Layers,
  Bug as BugIcon,
  CheckCircle2,
  AlertTriangle,
  Clock,
  PlayCircle,
  Camera,
  Video,
  FileCode,
  FileSearch,
  ExternalLink,
  Sparkles,
  ArrowRight,
  Shield,
  Activity,
} from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { setSelectedRunId } = useUiStore();

  const { data: stats, isLoading: isStatsLoading } = useStats();
  const { data: runs, isLoading: isRunsLoading } = useRuns();

  // Find the most recent active or latest run for the live column
  const activeRun = useMemo(() => {
    if (!runs || runs.length === 0) return null;
    const active = runs.find(
      (r) =>
        r.status !== "completed" &&
        r.status !== "failed" &&
        r.status !== "cancelled" &&
        r.status !== "budget_exhausted"
    );
    return active || runs[0];
  }, [runs]);

  // Connect live SSE stream to active run
  const isTerminalRun =
    activeRun?.status === "completed" ||
    activeRun?.status === "failed" ||
    activeRun?.status === "cancelled" ||
    activeRun?.status === "budget_exhausted";

  const { logs, clearLogs, connectionState } = useRunStream(
    activeRun?.id,
    isTerminalRun
  );

  // Find latest run that has "awaiting_review"
  const awaitingReviewRun = useMemo(() => {
    if (!runs) return null;
    return runs.find((r) => r.status === "awaiting_review") || activeRun;
  }, [runs, activeRun]);

  const { data: catalogTests, isLoading: isCatalogLoading } = useCatalog(
    awaitingReviewRun?.id
  );
  const pendingTests = useMemo(() => {
    return (catalogTests || []).filter((t) => t.review_status === "pending");
  }, [catalogTests]);

  const [selectedTestIds, setSelectedTestIds] = useState<string[]>([]);
  const { mutate: submitReview, isPending: isSubmittingReview } =
    useSubmitReview(awaitingReviewRun?.id || "");

  const handleApproveSelected = () => {
    if (selectedTestIds.length === 0 || !awaitingReviewRun) return;
    submitReview(
      {
        test_ids: selectedTestIds,
        decision: "approved",
        reason: "Approved from dashboard review gate",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "Tests approved",
            message: `${selectedTestIds.length} test(s) approved for execution`,
          });
          setSelectedTestIds([]);
        },
      }
    );
  };

  const handleApproveAll = () => {
    if (pendingTests.length === 0 || !awaitingReviewRun) return;
    const allIds = pendingTests.map((t) => t.id);
    submitReview(
      {
        test_ids: allIds,
        decision: "approved",
        reason: "All pending tests approved from dashboard",
      },
      {
        onSuccess: () => {
          toast({
            type: "success",
            title: "All tests approved",
            message: `${allIds.length} tests approved. Execution starting.`,
          });
          setSelectedTestIds([]);
        },
      }
    );
  };

  // Recent bugs from active or most recent run
  const { data: recentBugs, isLoading: isBugsLoading } = useBugs(
    activeRun?.id
  );

  const handleRunSelect = (runId: string) => {
    setSelectedRunId(runId);
    router.push(`/execution/${runId}`);

// ... [OMITTED 554 LINES (Total: 754 LOC)] ...

        </div>
      </section>

      {/* 5. SPECIAL FEATURE STRIP */}
      <section className="rounded-[16px] p-6 bg-[#F0EEE6] border-l-4 border-l-[#D97757] border border-[#E3DACC] shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-3xl">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#FAF9F5] border border-[#E3DACC] text-[#D97757] text-[11px] font-semibold uppercase tracking-wider">
              <Sparkles className="w-3 h-3 fill-[#D97757]" />
              Special feature
            </div>

            <h3 className="font-heading text-xl font-normal text-[#141413]">
              Verified, not guessed
            </h3>

            <p className="text-xs text-[#6B6A64] leading-relaxed">
              Every suspected bug is replayed 3 times by a deterministic verifier.
              No LLM decides the result. Statuses are honest:{" "}
              <strong className="text-[#141413]">Confirmed (3/3)</strong>,{" "}
              <strong className="text-[#141413]">Flaky (1-2/3)</strong>, or{" "}
              <strong className="text-[#141413]">Not reproduced (0/3)</strong>.
            </p>

            <p className="text-xs text-[#D97757] italic font-medium pt-1">
              &ldquo;It doesn&apos;t just report bugs. It proves them.&rdquo;
            </p>
          </div>

          <div className="shrink-0 flex items-center gap-2">
            <div className="p-3 rounded-xl bg-white border border-[#E3DACC] text-center shadow-xs">
              <div className="font-mono text-sm font-bold text-[#5E8C61]">
                3 of 3
              </div>
              <div className="text-[10px] text-[#8A887F] uppercase tracking-wider">
                Deterministic
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 6. FOOTER */}
      <footer className="pt-6 border-t border-[#E3DACC] text-center text-xs text-[#8A887F]">
        Runs only on authorized staging or local targets • Sandboxed with Docker •
        Human or AI review gate before execution
      </footer>
    </div>
  );
}
```

### `apps/web/src/app/execution/[runId]/page.tsx` (Run Detail Page)
```tsx
"use client";

import { ExecutionCockpit } from "@/features/runs/components/ExecutionCockpit";

export default function ExecutionRunPage() {
  return <ExecutionCockpit />;
}

```

### `apps/web/src/shared/ui/DataTable.tsx` (Representative Table)
```tsx
import React from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "./Skeleton";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render?: (row: T) => React.ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  isLoading?: boolean;
  emptyState?: React.ReactNode;
  onRowClick?: (row: T) => void;
  className?: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  isLoading = false,
  emptyState,
  onRowClick,
  className,
}: DataTableProps<T>) {
  return (
    <div
      className={cn(
        "w-full overflow-x-auto rounded-[16px] border border-[#E3DACC] bg-white shadow-xs",
        className
      )}
    >
      <table className="w-full text-left text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#E3DACC] bg-[#FAF9F5] text-xs font-medium text-[#6B6A64]">
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn("px-4 py-3 font-semibold", col.headerClassName)}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>

        <tbody className="divide-y divide-[#E3DACC]/60">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, rIdx) => (
              <tr key={rIdx}>
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3.5">
                    <Skeleton className="h-4 w-3/4" />
                  </td>
                ))}
              </tr>
            ))
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center">
                {emptyState || (
                  <span className="text-xs text-[#8A887F]">No data found</span>
                )}
              </td>
            </tr>
          ) : (
            data.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  "hover:bg-[#FAF9F5]/70 transition-colors",
                  onRowClick && "cursor-pointer"
                )}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "px-4 py-3.5 text-xs text-[#141413] align-middle",
                      col.className
                    )}
                  >
                    {col.render
                      ? col.render(row)
                      : (row[col.key] as React.ReactNode) ?? "-"}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

```

### `apps/web/src/shared/ui/Chip.tsx` (Representative Badge / Status)
```tsx
import React from "react";
import { cn } from "@/lib/utils";

export type ChipVariant =
  | "confirmed"
  | "passed"
  | "flaky"
  | "not_reproduced"
  | "failed"
  | "suspected"
  | "verifying"
  | "queued"
  | "running"
  | "pending"
  | "approved"
  | "rejected"
  | "skipped"
  | "error"
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "neutral"
  | "clay";

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant | string;
  size?: "xs" | "sm" | "md";
  dot?: boolean;
}

export function Chip({
  className,
  variant = "neutral",
  size = "sm",
  dot = false,
  children,
  ...props
}: ChipProps) {
  // Normalize string to match variants
  const v = (variant || "").toLowerCase();

  let styles = "bg-[#F2F1EE] text-[#6B6A64] border-[#E3DACC]";
  let dotColor = "bg-[#8A887F]";

  if (v === "confirmed" || v === "passed" || v === "approved" || v === "low") {
    styles = "bg-[#EBF2EB] text-[#47704A] border-[#D2E3D3]";
    dotColor = "bg-[#5E8C61]";
  } else if (v === "flaky" || v === "medium") {
    styles = "bg-[#FBF4E6] text-[#A67319] border-[#F4E2BD]";
    dotColor = "bg-[#D4A02A]";
  } else if (
    v === "not_reproduced" ||
    v === "failed" ||
    v === "rejected" ||
    v === "critical" ||
    v === "high" ||
    v === "error"
  ) {
    styles = "bg-[#FAEBE9] text-[#B83E31] border-[#F2CAC5]";
    dotColor = "bg-[#C4473A]";
  } else if (v === "clay") {
    styles = "bg-[#F6EDE8] text-[#C15F3C] border-[#F0D5C9]";
    dotColor = "bg-[#D97757]";
  } else if (v === "running" || v === "verifying" || v === "exploring" || v === "planning" || v === "executing") {
    styles = "bg-[#F5F2EB] text-[#7A6D52] border-[#E5DFCE]";
    dotColor = "bg-[#D97757] animate-pulse";
  }

  const sizeStyles = {
    xs: "text-[11px] px-1.5 py-0.5 rounded-md",
    sm: "text-xs px-2.5 py-0.5 rounded-full",
    md: "text-sm px-3 py-1 rounded-full",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-medium border whitespace-nowrap select-none",
        styles,
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotColor)} />}
      <span>{children}</span>
    </span>
  );
}

```

### `apps/web/src/shared/ui/Card.tsx` (Representative Card)
```tsx
import React from "react";
import { cn } from "@/lib/utils";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "bordered";
}

export function Card({
  className,
  variant = "default",
  children,
  ...props
}: CardProps) {
  const variantStyles = {
    default: "bg-white border border-[#E3DACC] shadow-[0_1px_2px_rgba(20,20,19,0.05)]",
    subtle: "bg-[#F0EEE6]/50 border border-[#E3DACC]/80",
    bordered: "bg-transparent border border-[#E3DACC]",
  };

  return (
    <div
      className={cn("rounded-[16px] p-5 transition-shadow", variantStyles[variant], className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex items-center justify-between pb-3 border-b border-[#E3DACC]/60 mb-4", className)} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("font-heading text-lg font-normal text-[#141413] tracking-tight", className)} {...props}>
      {children}
    </h3>
  );
}

```

### `apps/web/src/shared/ui/Dialog.tsx` (Representative Modal)
```tsx
"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogPortal = DialogPrimitive.Portal;
export const DialogClose = DialogPrimitive.Close;

export const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-[#141413]/30 backdrop-blur-xs transition-opacity duration-200",
      className
    )}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border border-[#E3DACC] bg-white p-6 shadow-xl rounded-[16px] duration-200 focus-visible:outline-none",
        className
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-lg p-1 text-[#8A887F] hover:text-[#141413] hover:bg-[#F0EEE6] transition-colors focus:outline-none cursor-pointer">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = DialogPrimitive.Content.displayName;

export const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-1.5 text-left border-b border-[#E3DACC]/60 pb-3",
      className
    )}
    {...props}
  />
);
DialogHeader.displayName = "DialogHeader";

export const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("font-heading text-lg font-normal text-[#141413]", className)}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

export const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-xs text-[#6B6A64] leading-relaxed", className)}
    {...props}
  />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;

export const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 pt-3 border-t border-[#E3DACC]/60",
      className
    )}
    {...props}
  />
);
DialogFooter.displayName = "DialogFooter";

```

---

## 11. SUGGESTED REFACTOR MAP

### File Migration & Refactor Mapping
| Current Path | Target Path (`design.md` §14.2) | Action | Notes |
| :--- | :--- | :--- | :--- |
| `components/` (all 28 files) | `src/components/ui/` & `src/components/kawach/` | **DELETE / MERGE** | Redundant clones of `src/shared/`. Merge unique changes into `src/components/` and delete root folder. |
| `hooks/useRunStream.ts` | `src/hooks/useRunStream.ts` | **MERGE / MOVE** | Standardize single SSE hook; add `stage` and `test.status` events. |
| `lib/` (all 6 files) | `src/lib/` | **DELETE / MERGE** | Redundant clones of `src/shared/lib/`. Merge and delete root `lib/`. |
| `src/app/page.tsx` | `src/app/(app)/page.tsx` | **SPLIT / REWRITE** | Split into clean Dashboard: extract Run Creator to `/runs/new`, active run monitor to `/runs/[id]`. |
| `src/app/start/page.tsx` | `src/app/(app)/runs/new/page.tsx` | **MOVE** | Standardize Run creation wizard under `/runs/new`. |
| `src/app/catalog/[runId]/page.tsx` | `src/app/(app)/runs/[id]/catalog/page.tsx` | **MOVE** | Nest catalog review gate under run ID scope. |
| `src/app/execution/[runId]/page.tsx` | `src/app/(app)/runs/[id]/live/page.tsx` | **REWRITE-IN-PLACE** | Fix broken import; connect live terminal and worker cards. |
| `src/app/results/[runId]/page.tsx` | `src/app/(app)/runs/[id]/bugs/page.tsx` | **MOVE** | Move bug results ledger to `/runs/[id]/bugs`. |
| `src/app/results/[runId]/bugs/[bugId]/page.tsx` | `src/app/(app)/runs/[id]/bugs/[bugId]/page.tsx` | **MOVE** | Standardize bug detail route. |
| `src/app/reports/[runId]/page.tsx` | `src/app/(app)/runs/[id]/report/page.tsx` | **MOVE** | Standardize report route. |
| `src/app/catalog/page.tsx` | `src/app/(app)/runs/page.tsx` | **MERGE** | Merge duplicate run pickers into one canonical Runs List page. |
| `src/app/execution/page.tsx` | None | **DELETE** | Redundant duplicate run picker. |
| `src/app/reports/page.tsx` | None | **DELETE** | Redundant duplicate run picker. |
| `src/app/results/page.tsx` | None | **DELETE** | Redundant duplicate run picker. |
| `src/app/debug/connection/page.tsx` | `src/app/debug/connection/page.tsx` | **KEEP** | Useful internal diagnostic tool. |
| `src/app/(app)/projects/[projectId]/commits/page.tsx` | None | **DELETE / ARCHIVE** | Unbacked by backend; archive or remove. |
| `src/app/(app)/projects/[projectId]/tests/page.tsx` | None | **DELETE / ARCHIVE** | Unbacked by backend; archive or remove. |
| `src/features/catalog/components/CatalogView.tsx` | `src/features/catalog/components/*` | **SPLIT** | Split 897 LOC file into `CatalogTable`, `TestEditDrawer`, `AddTestModal`, `ReviewActionBar`. |
| `src/features/reports/components/ReportView.tsx` | `src/features/report/components/*` | **SPLIT** | Split 717 LOC file into `ReportKpis`, `ReportMarkdown`, `ReportExports`, `ResultsDonut`. |
| `src/features/results/components/BugDetailView.tsx` | `src/features/bugs/components/*` | **SPLIT** | Split 525 LOC file into `BugVerificationTimeline`, `EvidenceViewer`, `ReproStepsLedger`. |
| `src/shared/ui/Stepper.tsx` | `src/components/kawach/RunStepper.tsx` | **REWRITE-IN-PLACE** | Upgrade from 6 stages to official 11 pipeline stages. |
| `src/shared/ui/CodeBlock.tsx` | `src/components/kawach/CodeWindow.tsx` | **REWRITE-IN-PLACE** | Add macOS window dots, Shiki syntax highlighter, copy button. |
| `src/shared/ui/LogViewer.tsx` | `src/components/kawach/Terminal.tsx` | **REWRITE-IN-PLACE** | Add auto-scroll pause pill, ANSI escape parser, search bar. |
| `src/shared/ui/*` | `src/components/ui/*` | **MOVE** | Standardize primitive components under `src/components/ui/`. |
| `src/shared/layout/*` | `src/components/layout/*` | **MOVE** | Move layout components out of `shared/`. |
| `types/index.ts` | `src/types/kawach.ts` | **MOVE / EXTEND** | Add `Health`, `Stats`, `Project`, and 11-stage definitions. |
| `middleware.ts` | `middleware.ts` | **REWRITE-IN-PLACE** | Fix `session_id` cookie check and enable guest route bypass. |
| `src/app/globals.css` | `src/styles/globals.css` | **REWRITE-IN-PLACE** | Replace with `design.md` Appendix A OKLCH token system. |

### 10-Step Safe Order of Operations
1. **Step 1: Fix Blockers (Middleware & Broken Imports)**
   - Add `session_id` to `middleware.ts`.
   - Fix broken imports in `src/app/execution/[runId]/page.tsx` and `src/app/(app)/projects/new/page.tsx`.
   - *Verification:* `npm run lint`
2. **Step 2: Eliminate Duplicate Root Folders**
   - Verify all unique references in root `components/`, `lib/`, `hooks/`.
   - Update `tsconfig.json` path mapping to `"@/*": ["./src/*"]`.
   - Remove root `components/`, `lib/`, `hooks/`.
   - *Verification:* `npx tsc --noEmit`
3. **Step 3: Install Required Dependencies & shadcn Baseline**
   - Install `recharts`, `react-markdown`, `rehype-sanitize`, `cmdk`, `sonner`, `d3-force`, `shiki`, `geist`.
   - Initialize `components.json` with CSS variables.
   - *Verification:* `npm run build`
4. **Step 4: Adopt Target Design System & CSS Tokens**
   - Drop `design.md` Appendix A into `src/styles/globals.css`.
   - Remove cursive Google Fonts; wire `Geist` and `JetBrains Mono` in root layout.
   - *Verification:* `npm run build`
5. **Step 5: Restructure App Router Routes to `/runs/[id]/*`**
   - Move scattered `/catalog/[runId]`, `/execution/[runId]`, `/results/[runId]`, `/reports/[runId]` under `/runs/[id]/*`.
   - Remove duplicate run picker listing pages (`/catalog`, `/execution`, `/reports`, `/results`).
   - *Verification:* `npx tsc --noEmit`
6. **Step 6: Upgrade Stepper & Pipeline Lifecycle to 11 Stages**
   - Update `RunStepper.tsx` and `types/kawach.ts` with the 11 pipeline stages.
   - Update `useRunStream.ts` to process `stage` and `test.status` SSE events.
   - *Verification:* `npx tsc --noEmit`
7. **Step 7: Decompose Giant Feature Views (<250 LOC per file)**
   - Split `CatalogView.tsx` (897 LOC) into modular components.
   - Split `ReportView.tsx` (717 LOC) and integrate `react-markdown` with `rehype-sanitize`.
   - Split `BugDetailView.tsx` (525 LOC) and `ResultsView.tsx` (513 LOC).
   - *Verification:* `npm run build`
8. **Step 8: Implement Missing Design System Components**
   - Build `AppMapGraph.tsx` using `d3-force` under `/runs/[id]/sitemap`.
   - Build `Timeline.tsx` ledger under `/runs/[id]/timeline`.
   - Build `CommandPalette.tsx` using `cmdk`.
   - *Verification:* `npm run build`
9. **Step 9: Add Global Error Boundaries & Loading Skeletons**
   - Add `not-found.tsx`, `error.tsx`, `global-error.tsx`, and route `loading.tsx` files.
   - *Verification:* `npm run build`
10. **Step 10: Purge Hardcoded Hex Classes & Final Verification**
    - Replace remaining hardcoded hex and arbitrary Tailwind classes with token classes.
    - *Verification:* `npm run lint && npm run build`

---

## 12. BASELINE HEALTH

- **Dependency Status:** `node_modules` was **NOT FOUND** in `apps/web`. Per explicit auditor instructions (*"Do NOT run install if node_modules does not exist; if it does not, say so and skip"*), package installation was omitted.
- **Static Analysis & Diagnostics Run:**
  - `check_imports`: Identified **3 broken import errors** that will fail `next build` immediately:
    1. `src/app/execution/[runId]/page.tsx:3` (Target `@/features/runs/components/ExecutionCockpit` does not exist)
    2. `src/app/(app)/projects/new/page.tsx:5` (Target `@/features/runs/components/StartTestForm` does not exist at that path)
    3. Missing root `components.json` and PostCSS configuration.
  - Linter configuration: `eslint.config.mjs` is valid, but ESLint execution cannot run without installed dependencies.

---

## EXECUTIVE SUMMARY

1. **Current State:** The frontend in `apps/web` has functional core feature coverage (Auth, Projects, Catalog Review, Bug Replays, and Report generation), but suffers from extreme architectural fragmentation: ~4,500 lines of duplicated code across two parallel component trees (`components/` vs `src/shared/`), 3 broken imports that prevent builds, and routes scattered across disconnected top-level paths instead of a unified `/runs/[id]` hierarchy.
2. **Top 5 Problems:**
   - **Build Blockers:** Broken imports in `execution/[runId]` and `projects/new` targeting non-existent modules.
   - **Auth Lockout:** `middleware.ts` ignores the backend's `session_id` cookie, trapping authenticated users in infinite redirect loops.
   - **Massive Duplication:** 27 components, API client, hooks, and mock services are cloned identically between root and `src/shared/`.
   - **Styling Chaos:** Zero OKLCH design tokens from `design.md` are present; the UI relies on 1,592 hardcoded hex colors, 1,770 arbitrary Tailwind overrides, and cursive script fonts.
   - **Giant Files & Missing Pages:** 6 monolithic files exceed 500 LOC (up to 897 LOC), while key specification routes (`/runs/[id]/sitemap`, `/runs/[id]/timeline`, `/settings`, error boundaries) are completely missing.
3. **Effort Estimate to Align with `design.md`:** **Medium (M)**. Because the foundational domain business logic, Zod validation, and SSE streaming pipeline are already functional, alignment does not require a rewrite. It requires an in-place structural consolidation: pruning duplicate trees, fixing cookie and import blockers, adopting Appendix A tokens, and reorganizing routes into `/runs/[id]/*`.
