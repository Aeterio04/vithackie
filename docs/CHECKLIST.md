# Autonomous AI QA Engineer — Project Checklist

## Phase 0: Foundations (23:40 – 00:20)
- [x] P0: Skeleton, models, storage, samples [Track B / Shared]

## Phase 1: Parallel Build (00:20 – 02:30)

### Track A: Target App & Ground Truth
- [ ] A1: Build demo target app with /signup, /login, /dashboard, /settings, /logout, /__reset [Track A]
- [ ] A2: Plant 9 bugs (GT01–GT09) and write spec.md (S1–S11) [Track A]
- [ ] A3: Write ground_truth.json and seed test user [Track A]

### Track B: Intelligence (LLM & Agents)
- [ ] B1: LLM client, prompt caching, cost tracking, prompts helper [Track B]
- [ ] B2: Explorer agent (crawler + LLM summary) [Track B]
- [ ] B3: Planner agent (test catalog with spec links) [Track B]
- [ ] B4: Script writer agent (Playwright .spec.ts generator) [Track B]
- [ ] B5: LangGraph graphs and STUB_MODE implementation [Track B]
- [ ] B6: Repro report agent [Track B]

### Track C: Execution & Platform
- [ ] C1: Playwright fixtures and smoke test [Track C]
- [ ] C2: Runner client and list_tests helper [Track C]
- [ ] C3: Run tests and collect evidence (traces, videos, screenshots, logs) [Track C]
- [ ] C4: Triage (assertion failures vs test errors) and verifier (3 replays) [Track C]
- [x] C5: FastAPI main application and report builder [Track C]

### Track D: Frontend (UI / UX)
- [ ] D1: Project setup and theme tokens [Track D]
- [ ] D2: Input form with URL allowlist and spec validation [Track D]
- [ ] D3: Live run view with stage progression and polling [Track D]
- [ ] D4: Catalog review table and add-test prompt modal [Track D]
- [ ] D5: Results and bugs view with 3x replay badges and evidence drawer [Track D]
- [ ] D6: Report view and passing tests export [Track D]

## Phase 2: Stitching (02:30 – 04:00)
- [ ] 2.1: Connect real API to frontend [All]
- [ ] 2.2: First full pipeline run end-to-end [All]
- [ ] 2.3: Prompt tuning on real app [Track B]
- [ ] 2.4: Evidence and replay verification check [Track C]
- [ ] 2.5: UI polish with real data [Track D]

## Phase 3: Should-Features and Safety (04:00 – 05:15)
- [ ] 3.1: Autonomous Reviewer agent with logged reasons [Track B]
- [ ] 3.2: Rule-based exploratory probes [Track B]
- [ ] 3.3: Export passing tests zip [Track C]
- [ ] 3.4: Parallel workers speedup measurement [Track C]
- [ ] 3.5: Network allowlist and safety checks [Track C]
- [ ] 3.6: Docker Compose setup [Track A]
- [ ] 3.7: One novelty / demo item [All]

## Phase 4: Benchmark and Demo Prep (05:15 – 06:30)
- [ ] 4.1: Tag release [All]
- [ ] 4.2: Benchmark against ground truth (recall, precision, replay rate) [Track A/C]
- [ ] 4.3: Golden run recording [All]
- [ ] 4.4: Fallback stub mode demo validation [All]
- [ ] 4.5: Slide deck and pitch rehearsal [All]

## Phase 5: Morning (06:30 – 08:30)
- [ ] 5.1: Preflight checks, rest, and demo rehearsal [All]
