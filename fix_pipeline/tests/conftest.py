"""Pytest fixtures and lightweight async runner hook for offline tests."""

import asyncio
import inspect
import json
import os
import sys
from pathlib import Path
import pytest
from pydantic import SecretStr

# Ensure fix_pipeline root, src, and tests are on python path
_tests_dir = Path(__file__).parent.resolve()
_root_dir = _tests_dir.parent.resolve()
_src_dir = (_root_dir / "src").resolve()
for p in (_root_dir, _src_dir, _tests_dir):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from tests.fakes import FakeGitHub, FakeLLM, FakeRunner
from kawach_fix.deps import Deps
from kawach_fix.schemas import ErrorReport, FixOptions, FixRequest


def pytest_pyfunc_call(pyfuncitem):
    """Run async test functions in an asyncio event loop without requiring pytest-asyncio."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        testfunction = pyfuncitem.obj
        funcargs = {
            arg: pyfuncitem.funcargs[arg]
            for arg in pyfuncitem._fixtureinfo.argnames
            if arg in pyfuncitem.funcargs
        }
        asyncio.run(testfunction(**funcargs))
        return True
    return None


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_request(fixtures_dir: Path) -> FixRequest:
    raw = json.loads((fixtures_dir / "sample_request.json").read_text(encoding="utf-8"))
    return FixRequest.model_validate(raw)


@pytest.fixture
def sample_proposal_json(fixtures_dir: Path) -> str:
    return (fixtures_dir / "sample_proposal.json").read_text(encoding="utf-8")


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def fake_llm(sample_proposal_json: str) -> FakeLLM:
    return FakeLLM(responses=[sample_proposal_json])


@pytest.fixture
def test_deps(tmp_path: Path, fake_runner: FakeRunner, fake_github: FakeGitHub, fake_llm: FakeLLM) -> Deps:
    return Deps(
        runner=fake_runner,
        github=fake_github,
        llm=fake_llm,
        runs_dir=tmp_path / "fix_runs",
    )
