"""Backwards compatibility shim for explorer agent forwarding to kawach.agents.explorer."""

import subprocess
import kawach.agents.explorer.agent as _agent_impl
from kawach.agents.explorer.agent import run_explorer, _extract_journeys_from_edges

__all__ = ["run_explorer", "subprocess", "_extract_journeys_from_edges"]
