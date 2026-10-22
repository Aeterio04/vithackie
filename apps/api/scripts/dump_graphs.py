"""Export Mermaid diagrams for Graph 1 and Graph 2.

Run with: python backend/scripts/dump_graphs.py
"""

import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
api_dir = repo_root / "apps" / "api"
sys.path.insert(0, str(api_dir))

from app.graphs import build_explore_plan_graph, build_execute_graph

def main():
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    g1 = build_explore_plan_graph()
    g2 = build_execute_graph()

    try:
        mmd1 = g1.get_graph().draw_mermaid()
    except Exception:
        mmd1 = "graph TD\n  explore --> plan\n  plan --> review_gate\n  review_gate --> END"

    try:
        mmd2 = g2.get_graph().draw_mermaid()
    except Exception:
        mmd2 = "graph TD\n  write_scripts --> run_tests\n  run_tests --> report_bugs\n  report_bugs --> verify\n  verify --> build_report\n  build_report --> END"

    path1 = docs_dir / "graph1.mmd"
    path2 = docs_dir / "graph2.mmd"

    path1.write_text(mmd1, encoding="utf-8")
    path2.write_text(mmd2, encoding="utf-8")

    print(f"Exported {path1}")
    print(f"Exported {path2}")
    print("\nGraph 1 Mermaid:\n", mmd1)
    print("\nGraph 2 Mermaid:\n", mmd2)

if __name__ == "__main__":
    main()
