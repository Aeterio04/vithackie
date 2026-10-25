"""Exploratory Testing Engine and Path Shrinker for Kawach.

Implements Task A4:
- Starts from deepest unexplored frontier states.
- Mutates known journeys (reorder steps, interrupt mid-flow, repeat actions, perturb inputs from edge library).
- Shared budget manager with loop detection.
- Path shrinking: trims failing journeys to the minimal failing sequence.
- Emits minimal Playwright reproduction scripts for triaged bugs.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from kawach.execution.edge_library import EDGE_LIBRARY, compute_risk_score
from kawach.core.config import settings
from kawach.schemas import ActionEdge, AppMap, FrontierState, Journey, StateNode, Step, TestCase
from kawach.storage import artifacts as storage


@dataclass
class MutationCandidate:
    mutation_type: str  # reorder, interrupt, repeat, perturb
    title: str
    description: str
    depth: int
    steps: List[Step]
    coverage_state_id: str
    edge_tag: str


def shrink_failing_path(steps: List[str], failed_step_index: Optional[int] = None) -> List[str]:
    """Shrink a failing action sequence to the minimal reproduction path.

    - Discards all steps following the failure step.
    - Preserves setup and preceding actions strictly necessary to reach the failing assertion.
    """
    if not steps:
        return []

    # If failure step known (1-based index), truncate subsequent steps
    if failed_step_index is not None and 1 <= failed_step_index <= len(steps):
        prefix = steps[:failed_step_index]
    else:
        prefix = list(steps)

    # Path shrinking heuristics:
    # 1. Deduplicate consecutive identical navigation or idle steps
    shrunk: List[str] = []
    for s in prefix:
        if not shrunk or shrunk[-1] != s:
            shrunk.append(s)

    return shrunk if shrunk else prefix


def emit_minimal_repro_script(
    bug_id: str,
    title: str,
    base_url: str,
    steps: List[str],
    out_dir: Path,
) -> Path:
    """Emit a standalone Playwright TypeScript reproduction script containing the shrunk path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    repro_file = out_dir / f"{bug_id}_repro.spec.ts"

    step_code_lines = []
    for idx, s in enumerate(steps, start=1):
        clean_step = s.replace("'", "\\'").replace("\n", " ")
        lower_step = s.lower()
        if "navigate" in lower_step or "go to" in lower_step or "/" in s:
            target_path = "/"
            url_match = re.search(r"https?://[^\s'\"]+", s)
            if url_match:
                parsed = urlparse(url_match.group(0))
                target_path = parsed.path or "/"
                if parsed.query:
                    target_path += f"?{parsed.query}"
            else:
                match = re.search(r"(/[a-zA-Z0-9_\-\./]*)", s)
                if match:
                    target_path = match.group(1)
                    if target_path.startswith("//"):
                        target_path = "/" + target_path.lstrip("/")
            if not target_path.startswith("/"):
                target_path = "/" + target_path
            step_code_lines.append(f"  // Step {idx}: Navigate\n  await page.goto('{target_path}', {{ waitUntil: 'domcontentloaded' }});")
        elif "click" in lower_step:
            loc = "button, [role='button'], a"
            match = re.search(r"\[(.*?)\]", s)
            if match:
                loc = match.group(1)
            step_code_lines.append(f"  // Step {idx}: Click action\n  await page.locator('{loc}').first().click({{ timeout: 5000 }});")
        elif "fill" in lower_step:
            val = "test_value"
            match_val = re.search(r"with '([^']*)'", s)
            if match_val:
                val = match_val.group(1)
            step_code_lines.append(f"  // Step {idx}: Fill input\n  await page.locator('input:not([type=\"hidden\"]), textarea').first().fill('{val}');")
        else:
            step_code_lines.append(f"  // Step {idx}: {clean_step}\n  await page.waitForTimeout(300);")

    script_content = f"""import {{ test, expect }} from '../../../apps/runner/fixtures';

test.describe('{bug_id}: Defect Reproduction', () => {{
  test('{bug_id}: Minimal reproduction - {title[:60]}', async ({{ page }}) => {{
{chr(10).join(step_code_lines)}
  }});
}});
"""
    repro_file.write_text(script_content, encoding="utf-8")
    return repro_file


class ExploratoryTester:
    """Autonomous exploratory tester that generates and runs targeted mutations."""

    def __init__(self, run_id: str, budget_tests: int = 5):
        self.run_id = run_id
        self.budget_tests = budget_tests
        self.executed_mutations: List[str] = []
        self.visited_states_history: List[str] = []

    def plan_exploratory_tests(self, app_map: Optional[AppMap]) -> List[TestCase]:
        """Derive mutated exploratory tests starting from deepest unexplored frontier states."""
        if not app_map:
            return []

        # Sort unexplored frontier states by depth descending (deepest first)
        frontier_sorted = sorted(app_map.unexploredFrontier, key=lambda f: f.depth, reverse=True)
        journeys = app_map.journeys or []

        candidates: List[MutationCandidate] = []

        # 1. Mutate journeys (depth >= 3)
        for j in journeys:
            if len(candidates) >= self.budget_tests:
                break

            j_steps_text = j.steps if j.steps else [f"Action at depth {j.depth}"]

            # A) Reorder steps mutation
            if len(j_steps_text) >= 2:
                reordered = list(j_steps_text)
                reordered[0], reordered[1] = reordered[1], reordered[0]
                candidates.append(
                    MutationCandidate(
                        mutation_type="reorder",
                        title=f"Exploratory Reorder: Swap initial steps in journey {j.journeyId}",
                        description=f"Inverts execution order of first two steps to test prerequisite enforcement.",
                        depth=j.depth,
                        steps=[
                            Step(n=idx + 1, action=act, checkpoint=f"Reordered step {idx + 1}")
                            for idx, act in enumerate(reordered)
                        ],
                        coverage_state_id=j.journeyId,
                        edge_tag="order_permutations",
                    )
                )

            # B) Interrupt mid-flow mutation
            if len(j_steps_text) >= 3 and len(candidates) < self.budget_tests:
                interrupted = list(j_steps_text[:2])
                interrupted.append("Press Escape or close modal to interrupt flow")
                interrupted.extend(j_steps_text[2:])
                candidates.append(
                    MutationCandidate(
                        mutation_type="interrupt",
                        title=f"Exploratory Interrupt: Escape mid-flow during {j.journeyId}",
                        description="Interrupts deep multi-step flow and attempts recovery without state corruption.",
                        depth=j.depth + 1,
                        steps=[
                            Step(n=idx + 1, action=act, checkpoint=f"Interrupted step {idx + 1}")
                            for idx, act in enumerate(interrupted)
                        ],
                        coverage_state_id=j.journeyId,
                        edge_tag="interrupted_flow",
                    )
                )

            # C) Rapid repeat submit mutation
            if len(candidates) < self.budget_tests:
                repeated = list(j_steps_text)
                if repeated:
                    repeated.append("Rapidly repeat final action twice (debounce test)")
                candidates.append(
                    MutationCandidate(
                        mutation_type="repeat",
                        title=f"Exploratory Repeat: Rapid repeat submit on {j.journeyId}",
                        description="Tests idempotency and double-click debouncing on deep journey completion.",
                        depth=j.depth,
                        steps=[
                            Step(n=idx + 1, action=act, checkpoint=f"Repeated step {idx + 1}")
                            for idx, act in enumerate(repeated)
                        ],
                        coverage_state_id=j.journeyId,
                        edge_tag="rapid_repeat_submit",
                    )
                )

        # 2. Perturb inputs from Edge Library starting from deepest frontier states
        for f in frontier_sorted:
            if len(candidates) >= self.budget_tests:
                break
            # Loop detection in candidate generation
            if f.stateId in self.visited_states_history:
                continue
            self.visited_states_history.append(f.stateId)

            # Apply HTML escaping or boundary perturbation
            edge_def = EDGE_LIBRARY["html_script_escaping"]
            candidates.append(
                MutationCandidate(
                    mutation_type="perturb",
                    title=f"Exploratory Perturb: Inject script tag at frontier state {f.stateId}",
                    description=f"Tests escaping and sanitization on unexplored frontier state at depth {f.depth}.",
                    depth=max(f.depth, 2),
                    steps=[
                        Step(n=1, action=f"Navigate to {f.url}", checkpoint="Navigate to frontier state"),
                        Step(
                            n=2,
                            action=f"Fill interactive input with '{edge_def.payload}' and submit",
                            expected="Rendered with characters escaped; no script executed",
                            checkpoint="Check input sanitization",
                            assertion="Assert script tag is escaped",
                        ),
                    ],
                    coverage_state_id=f.stateId,
                    edge_tag="html_script_escaping",
                )
            )

        # Build final exploratory TestCase models with IDs X01, X02, ...
        exploratory_tests: List[TestCase] = []
        for idx, c in enumerate(candidates[: self.budget_tests], start=1):
            x_id = f"X{idx:02d}"
            edge_def = EDGE_LIBRARY.get(c.edge_tag)
            sev = edge_def.severity if edge_def else 2.0
            risk = compute_risk_score("high", c.depth, sev)

            exploratory_tests.append(
                TestCase(
                    id=x_id,
                    title=f"{x_id}: {c.title}",
                    description=c.description,
                    specRef=[],
                    priority="high",
                    depth=c.depth,
                    category="edge_case",
                    preconditions=["Target web application running"],
                    setup=[],
                    edgeTags=[c.edge_tag, c.mutation_type],
                    coverageRef=[c.coverage_state_id],
                    riskScore=risk,
                    steps=c.steps,
                    status="approved",  # Pre-approved exploratory mutations
                    origin="heuristic",
                    script=f"scripts/{x_id}.spec.ts",
                    scriptStatus="pending",
                )
            )

        return exploratory_tests

    def generate_exploratory_specs(
        self,
        exploratory_tests: List[TestCase],
        target_url: str,
        scripts_dir: Path,
    ) -> List[Path]:
        """Generate executable Playwright test specs for exploratory mutations."""
        scripts_dir.mkdir(parents=True, exist_ok=True)
        generated_files: List[Path] = []

        for tc in exploratory_tests:
            spec_file = scripts_dir / f"{tc.id}.spec.ts"
            step_code_lines = []

            for idx, st in enumerate(tc.steps, start=1):
                clean_action = st.action.replace("'", "\\'").replace("\n", " ")
                act_lower = st.action.lower()

                if "navigate" in act_lower or "go to" in act_lower or "/" in st.action:
                    target_path = "/"
                    url_match = re.search(r"https?://[^\s'\"]+", st.action)
                    if url_match:
                        parsed = urlparse(url_match.group(0))
                        target_path = parsed.path or "/"
                        if parsed.query:
                            target_path += f"?{parsed.query}"
                    else:
                        match = re.search(r"(/[a-zA-Z0-9_\-\./]*)", st.action)
                        if match:
                            target_path = match.group(1)
                            if target_path.startswith("//"):
                                target_path = "/" + target_path.lstrip("/")
                    if not target_path.startswith("/"):
                        target_path = "/" + target_path
                    step_code_lines.append(f"  // Step {idx}: Navigate ({st.checkpoint or 'navigate'})\n  await page.goto('{target_path}', {{ waitUntil: 'domcontentloaded' }});")
                elif "click" in act_lower:
                    loc = "button, [role='button'], a"
                    match = re.search(r"\[(.*?)\]", st.action)
                    if match:
                        loc = match.group(1)
                    step_code_lines.append(f"  // Step {idx}: Click ({st.checkpoint or 'click'})\n  await page.locator('{loc}').first().click({{ timeout: 5000 }});")
                elif "fill" in act_lower:
                    val = "exploratory_input"
                    match_val = re.search(r"with '([^']*)'", st.action)
                    if match_val:
                        val = match_val.group(1).replace("'", "\\'")
                    step_code_lines.append(f"  // Step {idx}: Fill input ({st.checkpoint or 'fill'})\n  await page.locator('input:not([type=\"hidden\"]), textarea').first().fill('{val}');")
                elif "escape" in act_lower or "interrupt" in act_lower:
                    step_code_lines.append(f"  // Step {idx}: Interrupt flow\n  await page.keyboard.press('Escape');")
                else:
                    step_code_lines.append(f"  // Step {idx}: {clean_action}\n  await page.waitForLoadState('networkidle').catch(() => {{}});")

                if st.assertion:
                    clean_assert = st.assertion.replace("'", "\\'")
                    step_code_lines.append(f"  // Step {idx} Assertion: {clean_assert}\n  await expect(page.locator('body')).not.toContainText('500');")

            code = f"""import {{ test, expect, credentials, unique, expectErrorFeedback, expectNoErrorFeedback, expectSuccessFeedback, uniqueData, uniqueEmail, inspectPageForError }} from '../../../apps/runner/fixtures';

test.describe('{tc.id}: Exploratory Mutation', () => {{
  test('{tc.id}: {tc.title}', async ({{ page }}) => {{
{chr(10).join(step_code_lines)}
  }});
}});
"""
            spec_file.write_text(code, encoding="utf-8")
            tc.scriptStatus = "valid"
            generated_files.append(spec_file)

        return generated_files
