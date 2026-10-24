# Kawach Demo Harness (`kawach_demo`)

A standalone, live demonstration harness for the **Kawach GitHub Fix Pipeline** (`kawach_fix`). The harness verifies real Playwright test failures, analyzes commit diffs on `origin/main`, queries real LLMs for targeted repairs, opens GitHub pull requests, and allows presenters to merge the fix and verify live hot-reload resolution.

---

## 🔒 Security & Privacy Guarantees

- **No Secrets Leaked**: GitHub Personal Access Tokens (PATs) and LLM API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`) are read strictly from `.env` or environment variables. They are **never** logged, printed to console, passed in CLI arguments, or embedded in URLs.
- **Git Credential Helper**: Git authentication utilizes a transient `GIT_ASKPASS` helper that injects credentials safely via process environment variables without command-line exposure.
- **Real Execution**: Zero canned, recorded, or mock LLM responses in the demo execution path. The pipeline interacts live with Groq / Gemini and GitHub.

---

## ⚙️ Prerequisites & Setup

### 1. Requirements
- Python 3.10+
- Node.js (with `npx` and Playwright installed in the target app repository)
- Git CLI

### 2. Required GitHub PAT Scopes
Your GitHub Personal Access Token must have permissions on the demo target repository (`DEMO_REPO`):
- **Fine-Grained PAT (Recommended)**:
  - Repository Permissions:
    - **Contents**: Read and Write
    - **Pull requests**: Read and Write
    - **Metadata**: Read-only (included automatically)
- **Classic PAT**:
  - `repo` (Full control of private repositories)

> **IMPORTANT**: Branch protection rules on the demo target repository **must be disabled** so the harness can plant bugs and reset `origin/main` back to `demo-good` via force push (`--force-with-lease`).

### 3. Environment Configuration (`.env`)
Create `kawach_demo/.env` (or copy `.env.example`):

```bash
# GitHub PAT
GITHUB_PAT=github_pat_11A...

# Target repository (owner/name)
DEMO_REPO=your-username/kawach-demo-shop

# Absolute path to local clone running dev server
APP_CLONE_PATH=C:/projects/target-app/kawach-demo-shop

# Local dev server URL
TARGET_URL=http://localhost:3000

# LLM Providers (at least one key required; Groq primary, Gemini fallback)
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIzaSy...

# Optional: Run artifacts directory
KAWACH_FIX_RUNS_DIR=./fix_runs
```

### 4. Target Application
Start the target app in a separate terminal:
```bash
cd C:/projects/target-app/kawach-demo-shop
npm run dev
# or: node --watch src/server.js
```
*Note: The harness never starts, stops, or modifies the running server process.*

---

## 📋 One-Page Presenter Runbook

Follow this exact sequence for a flawless live demo presentation:

```bash
# Step 1: Preflight Health Check
# Verifies target app is online, PAT scopes, LLM connectivity, clone clean on demo-good
python -m kawach_demo preflight

# Step 2: Clean Baseline State
# Closes stale fix PRs, deletes remote branches, and aligns clone with demo-good
python -m kawach_demo reset

# Step 3: Optional Automated Rehearsal Matrix
# Evaluates candidates in dry-run mode and prints reliability scoreboard
python -m kawach_demo rehearse --bugs 1,2,3 --times 2

# Step 4: Final Reset Before Live Stage
python -m kawach_demo reset

# Step 5: Full Jury Live Demonstration Flow
# Runs Scenes 1 through 5 with interactive presenter pauses
python -m kawach_demo full --bug 1
```

*(Tip: Pass `--no-pause` to run the demonstration unattended without presenter Enter prompts).*

---

## 🎬 Demo Scene Breakdown

1. **Scene 1: "Healthy Baseline"**
   - Executes Playwright test (`tests/cart.spec.ts`) against `TARGET_URL`.
   - Confirms green regression baseline.
2. **Scene 2: "The Bad Commit"**
   - Applies bug patch (`bugs/bug_1.patch`) with innocent commit message (e.g., `refactor: extract pricing helpers`).
   - Pushes commit to `origin/main`.
   - Re-runs test to observe live failure (`$57.00` vs `$61.56`).
3. **Scene 3: "Negative Control Gate"**
   - Dispatches a phantom bug report against `tests/home.spec.ts` (which is healthy).
   - Replay verifier stops execution: `not_reproduced`.
   - Narrator highlights: *"Kawach does not trust error reports blindly."*
4. **Scene 4: "Autonomous Defect Verification & PR Repair"**
   - Replays defect 3x to confirm persistence.
   - Inspects latest commit on `origin/main`.
   - LLM synthesizes exact search-and-replace edit.
   - Validates edit against commit scope and file contents.
   - Opens Pull Request on GitHub and renders colored before/after diff.
5. **Scene 5: "Human in the Loop"**
   - Prompts presenter with PR URL to review and merge on GitHub.
   - Once merged, pulls `origin/main` into local clone.
   - Hot reload applies changes; test suite passes green.
6. **Optional Scene G: "Adversarial Model Guardrail" (`--with-guardrail-scene`)**
   - Simulates malicious/unauthorized model output attempting to edit uncommitted security files.
   - Demonstrates Kawach pipeline immediately blocking the edit (`invalid_llm_output`).

---

## 🐛 Bug Catalog

| Bug ID | Difficulty | Title | Commit Message | Causal File | Decoy Edits |
|---|---|---|---|---|---|
| `bug_1` | Easy | Drop tax from total quote | `refactor: extract pricing helpers` | `src/pricing.js` | `src/format.js`, `src/items.js` |
| `bug_2` | Medium | Double discount deduction | `refactor: extract discount calculation helper` | `src/pricing.js` | `src/discounts.js`, `src/format.js` |
| `bug_3` | Hard | Floating point quote drift | `refactor: streamline quote pricing calculations` | `src/pricing.js` | `src/format.js`, `src/items.js` |

---

## 🛠️ Troubleshooting

### 1. "LLM Rate Limit / 429"
`kawach_demo` uses `ResilientLLMChain`. If Groq encounters rate limiting or timeouts, it retries with exponential backoff before seamlessly falling back to Google Gemini (`gemini-2.5-flash`). Both keys should be configured for high availability.

### 2. "Target app connection refused"
Ensure `npm run dev` or `node --watch src/server.js` is running at `TARGET_URL` (`http://localhost:3000`). Run `python -m kawach_demo preflight` to confirm.

### 3. "Pull Request already exists (`pr_exists`)"
Run `python -m kawach_demo reset` to close existing pull requests and delete leftover `kawach/fix-*` branches before running the demo.

### 4. "Git push rejected (--force-with-lease)"
Ensure branch protection is turned **OFF** on your GitHub target demo repository.
