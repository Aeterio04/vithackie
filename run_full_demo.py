"""
KAWACH Full Demo - Complete End-to-End Agentic QA Workflow
1. Starts target app on localhost:4000
2. Runs dual-graph agentic system with Groq LLM
3. Executes Playwright tests with real browser
4. Generates verification report
"""

import sys
import os
import subprocess
import time
import requests
from pathlib import Path

sys.path.insert(0, os.path.join(os.getcwd(), "apps", "api", "src"))

# Force reload settings
import importlib
from kawach.core import config as config_module
importlib.reload(config_module)
from kawach.core.config import settings

print("=" * 80)
print("KAWACH AUTONOMOUS AI QA ENGINEER - FULL DEMO")
print("=" * 80)
print()

# Step 1: Verify Playwright is installed
print("STEP 1: Verifying Playwright Installation")
print("-" * 80)
try:
    result = subprocess.run(
        ["npx", "playwright", "--version"],
        cwd="apps/runner",
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.returncode == 0:
        print(f"✓ Playwright installed: {result.stdout.strip()}")
    else:
        print("✗ Playwright not found. Installing...")
        subprocess.run(["npx", "playwright", "install", "chromium"], cwd="apps/runner", check=True)
        print("✓ Playwright installed")
except Exception as e:
    print(f"✗ Playwright check failed: {e}")
    print("  Run: cd apps/runner && npx playwright install chromium")

print()

# Step 2: Start target app
print("STEP 2: Starting Target Application")
print("-" * 80)
print("Starting server on http://localhost:4000...")

target_process = subprocess.Popen(
    ["node", "server.js"],
    cwd="examples/target-app",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Wait for server to be ready
time.sleep(3)
try:
    response = requests.get("http://localhost:4000", timeout=5)
    if response.status_code == 200:
        print("✓ Target app running on http://localhost:4000")
    else:
        print(f"✗ Server returned status {response.status_code}")
        target_process.terminate()
        sys.exit(1)
except Exception as e:
    print(f"✗ Cannot connect to target app: {e}")
    print("  Make sure port 4000 is available")
    target_process.terminate()
    sys.exit(1)

print()

# Step 3: Load spec from target app
print("STEP 3: Loading Specification")
print("-" * 80)
spec_path = Path("examples/target-app/spec.md")
spec_raw = spec_path.read_text(encoding="utf-8")
print(f"✓ Loaded spec: {len(spec_raw.splitlines())} requirements")
print()

# Step 4: Configure Groq
print("STEP 4: Groq LLM Configuration")
print("-" * 80)
print(f"Model: {settings.LLM_MODEL}")
print(f"RPM Limit: {settings.GROQ_RPM_LIMIT}")
print(f"TPM Limit: {settings.GROQ_TPM_LIMIT}")
print(f"Min Interval: {settings.GROQ_MIN_INTERVAL}s")
print(f"Cache: {settings.LLM_CACHE}")
print()

# Step 5: Create run
print("STEP 5: Creating Test Run")
print("-" * 80)

from kawach.workflows import run_explore_plan, run_execute
from kawach.storage import artifacts as storage
from kawach.core.ids import new_run_id
from kawach.core.clock import now_iso
from kawach.services.spec_parser import parse_spec_raw
from kawach.schemas import RunInput, Run, Budgets
from kawach.storage.secrets import write_secret_password

run_id = new_run_id()

# Read test credentials from target app (default credentials)
username = "qa.tester@example.com"
password = "Passw0rd!23"

run_input = RunInput(
    runId=run_id,
    createdAt=now_iso(),
    targetUrl="http://localhost:4000",
    prompt="",
    specRaw=spec_raw,
    spec=parse_spec_raw(spec_raw),
    username=username,
    mode="autonomous",
    budgets=Budgets(maxPages=10, exploreSeconds=90, maxTests=11),
)
storage.save_model(run_id, "input.json", run_input)
write_secret_password(run_id, password)

run = Run(
    runId=run_id,
    createdAt=run_input.createdAt,
    updatedAt=run_input.createdAt,
    stage="created",
    mode="autonomous",
    targetUrl=run_input.targetUrl,
)
storage.save_model(run_id, "run.json", run)

print(f"✓ Run ID: {run_id}")
print(f"  Target: {run_input.targetUrl}")
print(f"  Mode: autonomous")
print(f"  Credentials: {username}")
print()

# Step 6: Execute Graph 1 (Explore & Plan)
print("=" * 80)
print("STEP 6: GRAPH 1 - EXPLORE & PLAN")
print("=" * 80)
print()
print("Nodes: explorer → planner → review_gate")
print()

try:
    run_explore_plan(run_id)
    print("✓ Graph 1 completed")
    
    # Show results
    catalog = storage.read_json(run_id, "catalog.json")
    if catalog:
        tests = catalog.get('tests', [])
        approved = sum(1 for t in tests if t.get('status') == 'approved')
        print(f"  - Tests planned: {len(tests)}")
        print(f"  - Auto-approved: {approved}")
        
        # Show first 3 tests
        print("\n  Sample tests:")
        for test in tests[:3]:
            print(f"    {test.get('id')}: {test.get('title', 'N/A')[:60]}")
except Exception as e:
    print(f"✗ Graph 1 failed: {e}")
    import traceback
    traceback.print_exc()
    target_process.terminate()
    sys.exit(1)

print()

# Step 7: Execute Graph 2 (Execute & Verify)
print("=" * 80)
print("STEP 7: GRAPH 2 - EXECUTE & VERIFY")
print("=" * 80)
print()
print("Nodes: write_scripts → run_tests → report_bugs → verify → build_report")
print()
print("This will take several minutes (Playwright execution + verification)...")
print()

try:
    run_execute(run_id)
    print("✓ Graph 2 completed")
    
    # Show results
    metrics_file = storage.run_dir(run_id) / "metrics.json"
    if metrics_file.exists():
        import json
        with open(metrics_file) as f:
            metrics = json.load(f)
        
        print("\n" + "=" * 80)
        print("FINAL RESULTS")
        print("=" * 80)
        print(f"\nExecution time: {metrics.get('wallClockSeconds', 0):.0f}s")
        print(f"\nTests:")
        print(f"  - Planned: {metrics.get('tests', {}).get('planned', 0)}")
        print(f"  - Passed: {metrics.get('tests', {}).get('passed', 0)}")
        print(f"  - Failed: {metrics.get('tests', {}).get('failed', 0)}")
        print(f"  - Errors: {metrics.get('tests', {}).get('errored', 0)}")
        
        print(f"\nBugs:")
        print(f"  - Confirmed: {metrics.get('bugs', {}).get('confirmed', 0)}")
        print(f"  - Flaky: {metrics.get('bugs', {}).get('flaky', 0)}")
        print(f"  - Not reproduced: {metrics.get('bugs', {}).get('notReproduced', 0)}")
        
        print(f"\nCoverage:")
        print(f"  - Spec items covered: {metrics.get('coverage', {}).get('specItemsCovered', 0)}/{metrics.get('coverage', {}).get('specItems', 0)}")
        
        print(f"\nLLM Usage:")
        print(f"  - API calls: {metrics.get('llm', {}).get('calls', 0)}")
        print(f"  - Cache hits: {metrics.get('llm', {}).get('cacheHits', 0)}")
        print(f"  - Input tokens: {metrics.get('llm', {}).get('inputTokens', 0):,}")
        print(f"  - Output tokens: {metrics.get('llm', {}).get('outputTokens', 0):,}")
        print(f"  - Cost: ${metrics.get('llm', {}).get('costUsd', 0):.4f}")
        
except Exception as e:
    print(f"✗ Graph 2 failed: {e}")
    import traceback
    traceback.print_exc()
    target_process.terminate()
    sys.exit(1)

print()
print("=" * 80)
print("DEMO COMPLETE")
print("=" * 80)
print(f"\nArtifacts: {storage.run_dir(run_id)}")
print(f"\nTo view the report:")
print(f"  cat {storage.run_dir(run_id)}/report.md")
print()

# Cleanup
print("Stopping target app...")
target_process.terminate()
target_process.wait(timeout=5)
print("✓ Cleanup complete")
