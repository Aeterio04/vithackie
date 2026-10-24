"""
Simulate KAWACH Agentic Workflow
Demonstrates the dual-graph LangGraph agentic system.
"""

import sys
import os

# Add kawach to path
sys.path.insert(0, os.path.join(os.getcwd(), "apps", "api", "src"))

import json
from kawach.core.config import settings

# Disable stub mode to use real Groq LLM
settings.STUB_MODE = False
settings.LLM_MODEL = "qwen/qwen3.8-27b"  # Force correct model
settings.GROQ_DEFAULT_MODEL = "qwen/qwen3.8-27b"

print(f"   • LLM Provider: {settings.LLM_PROVIDER}")
print(f"   • LLM Model: {settings.LLM_MODEL}")
print(f"   • Groq TPM Limit: {settings.GROQ_TPM_LIMIT}")
print(f"   • Groq RPM Limit: {settings.GROQ_RPM_LIMIT}")

print("=" * 80)
print("KAWACH AGENTIC WORKFLOW SIMULATION")
print("=" * 80)
print()

print("System Configuration:")
print(f"   * Stub Mode: {settings.STUB_MODE}")
print(f"   • Runs Directory: {settings.runs_dir}")

# Import the workflow modules
from kawach.workflows import run_explore_plan, run_execute
from kawach.storage import artifacts as storage

print("=" * 80)
print("CREATING TEST RUN")
print("=" * 80)
print()

# Create a test run using the service
target_url = "http://localhost:4000"
spec_raw = """S1: Users can sign up with email and password
S2: Users can log in with credentials
S3: Users can manage todo items"""

print(f"Target: {target_url}")
print(f"Spec: {spec_raw[:60]}...")
print(f"Mode: autonomous")
print()

# Create run using service (but don't auto-start background thread)
from kawach.core.ids import new_run_id
from kawach.core.clock import now_iso
from kawach.services.spec_parser import parse_spec_raw
from kawach.schemas import RunInput, Run, Budgets
from kawach.storage.secrets import write_secret_password

run_id = new_run_id()
created_at = now_iso()
spec_items = parse_spec_raw(spec_raw)

run_input = RunInput(
    runId=run_id,
    createdAt=created_at,
    targetUrl=target_url,
    prompt="",
    specRaw=spec_raw,
    spec=spec_items,
    username="test@example.com",
    mode="autonomous",
    budgets=Budgets(),
)
storage.save_model(run_id, "input.json", run_input)
write_secret_password(run_id, "testpass123")

run = Run(
    runId=run_id,
    createdAt=created_at,
    updatedAt=created_at,
    stage="created",
    mode="autonomous",
    targetUrl=target_url,
)
storage.save_model(run_id, "run.json", run)

print(f"Run ID: {run_id}")
print("Run initialized")
print()

print("=" * 80)
print("GRAPH 1: EXPLORE & PLAN")
print("=" * 80)
print()

print("Starting exploration and planning workflow...")
print()
print("   Node Sequence:")
print("   1. Explorer Agent  -> BFS crawler + LLM app map")
print("   2. Planner Agent   -> Test catalog with spec coverage")
print("   3. Review Gate     -> Autonomous approval")
print()

try:
    run_explore_plan(run_id)
    print("Graph 1 completed successfully")
    
    # Show the app map
    try:
        app_map = storage.load_json(run_id, "app_map.json")
        if app_map:
            print()
            print("App Map Generated:")
            print(f"   * Pages discovered: {len(app_map.get('pages', []))}")
            print(f"   * Summary: {app_map.get('summary', 'N/A')[:60]}...")
    except:
        pass
    
    # Show the catalog
    try:
        catalog = storage.load_json(run_id, "catalog.json")
        if catalog:
            print()
            print("Test Catalog Generated:")
            print(f"   * Total tests: {len(catalog.get('tests', []))}")
            approved = sum(1 for t in catalog.get('tests', []) if t.get('status') == 'approved')
            print(f"   * Approved tests: {approved}")
    except:
        pass
        
except Exception as e:
    print(f"Graph 1 failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("GRAPH 2: EXECUTE & VERIFY")
print("=" * 80)
print()

print("Starting execution workflow...")
print()
print("   Node Sequence:")
print("   1. Script Writer    -> Generate Playwright tests")
print("   2. Test Runner      -> Execute in browser sandboxes")
print("   3. Bug Reporter     -> Synthesize defect reports")
print("   4. Verifier         -> 3x replay verification")
print("   5. Report Builder   -> Final metrics & report")
print()

try:
    run_execute(run_id)
    print("Graph 2 completed successfully")
    
    # Show execution results
    try:
        results = storage.load_json(run_id, "results.json")
        if results:
            print()
            print("Execution Results:")
            print(f"   * Total tests: {results.get('totalTests', 0)}")
            print(f"   * Passed: {results.get('passed', 0)}")
            print(f"   * Failed: {results.get('failed', 0)}")
    except:
        pass
    
    # Show bugs
    try:
        bugs = storage.load_json(run_id, "bugs.json")
        if bugs and bugs.get('bugs'):
            print()
            print("Bugs Found:")
            for bug in bugs['bugs'][:3]:  # Show first 3
                print(f"   * {bug.get('title', 'N/A')}")
    except:
        pass
        
    # Show metrics
    try:
        metrics = storage.load_json(run_id, "metrics.json")
        if metrics:
            print()
            print("Final Metrics:")
            print(f"   * Workflow completion: {metrics.get('workflowCompletionPct', 0)}%")
            print(f"   * Finding verification: {metrics.get('findingVerificationPct', 0)}%")
    except:
        pass
        
except Exception as e:
    print(f"Graph 2 failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("SIMULATION COMPLETE")
print("=" * 80)
print()

# Show final run status
try:
    run = storage.get_run(run_id)
    print(f"Final Status: {run.stage}")
    print(f"Artifacts stored in: {storage.run_dir(run_id)}")
except:
    pass

print()
print("To explore the generated artifacts:")
print(f"   cd {storage.run_dir(run_id)}")
print("   ls")
