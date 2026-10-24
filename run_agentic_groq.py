"""
KAWACH Agentic Workflow - Groq Rate Limit Optimized
Demonstrates dual-graph LangGraph system with aggressive rate limiting strategy.

GROQ LIMITS (qwen/qwen3.8-27b):
- 30 RPM, 8K TPM (tokens per minute includes input+output+max_tokens reservation)
- Strategy: 50% token reduction, 2.5s pacing, aggressive caching
"""

import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), "apps", "api", "src"))

# Force reload settings
import importlib
from kawach.core import config as config_module
importlib.reload(config_module)
from kawach.core.config import settings

print("=" * 80)
print("GROQ RATE LIMIT OPTIMIZATION STRATEGY")
print("=" * 80)
print(f"\nModel: {settings.LLM_MODEL}")
print(f"RPM Limit: {settings.GROQ_RPM_LIMIT} | TPM Limit: {settings.GROQ_TPM_LIMIT}")
print(f"Min Interval: {settings.GROQ_MIN_INTERVAL}s | Cache: {settings.LLM_CACHE}")
print("\nOptimizations Applied:")
print("  - Token budgets reduced ~40% across all agents")
print("  - Min request spacing increased to 2.5s")
print("  - Proactive TPM sliding window tracking")
print("  - Disk cache enabled for all calls")
print()

from kawach.workflows import run_explore_plan, run_execute
from kawach.storage import artifacts as storage
from kawach.core.ids import new_run_id
from kawach.core.clock import now_iso
from kawach.services.spec_parser import parse_spec_raw
from kawach.schemas import RunInput, Run, Budgets
from kawach.storage.secrets import write_secret_password

# Create run
run_id = new_run_id()
spec_raw = """S1: Users can sign up
S2: Users can log in
S3: Users can manage items"""

run_input = RunInput(
    runId=run_id,
    createdAt=now_iso(),
    targetUrl="http://localhost:4000",
    prompt="",
    specRaw=spec_raw,
    spec=parse_spec_raw(spec_raw),
    username="test@example.com",
    mode="autonomous",
    budgets=Budgets(),
)
storage.save_model(run_id, "input.json", run_input)
write_secret_password(run_id, "testpass123")

run = Run(
    runId=run_id,
    createdAt=run_input.createdAt,
    updatedAt=run_input.createdAt,
    stage="created",
    mode="autonomous",
    targetUrl=run_input.targetUrl,
)
storage.save_model(run_id, "run.json", run)

print("=" * 80)
print(f"RUN CREATED: {run_id}")
print("=" * 80)
print()

# GRAPH 1: Explore & Plan
print("GRAPH 1: EXPLORE & PLAN")
print("-" * 80)
print("Nodes: explorer -> planner -> review_gate")
print()

try:
    run_explore_plan(run_id)
    print("\nGraph 1 completed")
    
    catalog = storage.load_json(run_id, "catalog.json")
    if catalog:
        tests = catalog.get('tests', [])
        print(f"  - Tests generated: {len(tests)}")
        approved = sum(1 for t in tests if t.get('status') == 'approved')
        print(f"  - Auto-approved: {approved}")
except Exception as e:
    print(f"\nGraph 1 error: {e}")
    import traceback
    traceback.print_exc()

print()

# GRAPH 2: Execute & Verify
print("=" * 80)
print("GRAPH 2: EXECUTE & VERIFY")
print("-" * 80)
print("Nodes: write_scripts -> run_tests -> report_bugs -> verify -> build_report")
print()

try:
    run_execute(run_id)
    print("\nGraph 2 completed")
    
    metrics = storage.load_json(run_id, "metrics.json")
    if metrics:
        print(f"  - Workflow completion: {metrics.get('workflowCompletionPct', 0)}%")
        print(f"  - Tests executed: {metrics.get('tests', {}).get('total', 0)}")
        print(f"  - Bugs found: {metrics.get('bugs', {}).get('total', 0)}")
        print(f"  - Confirmed: {metrics.get('bugs', {}).get('confirmed', 0)}")
except Exception as e:
    print(f"\nGraph 2 error: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("EXECUTION COMPLETE")
print("=" * 80)
print(f"\nArtifacts: {storage.run_dir(run_id)}")
