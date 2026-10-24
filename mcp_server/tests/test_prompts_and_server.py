import httpx
import pytest

from kawach_mcp import server as server_mod
from kawach_mcp.errors import KawachError
from kawach_mcp.server import SERVER_NAME, create_server, probe_backend
from kawach_mcp.tools import READ, tool
from conftest import API

EXPECTED_PROMPTS = {
    "qa_full_run": ["health_check", "check_target", "upload_spec", "run_qa_pipeline", "awaiting_review", "wait_for_run", "get_run_summary", "STOP"],
    "review_catalog": ["get_catalog", "include_steps=True", "reason", "go-ahead", "review_tests", "add_test", "no separate resume"],
    "triage_and_fix": ["get_run_summary", "get_bug_fix_context", "save_repro_script", "retest_after_fix", "STOP and ask"],
    "regression_check": ["retest_after_fix", "compare_runs", "persist"],
    "explain_run": ["get_run_summary", "get_report", "get_app_map", "stakeholder"],
}


async def test_five_prompts_registered_with_arguments_and_tool_names():
    server = create_server()
    prompts = {p.name: p for p in await server.list_prompts()}
    assert set(prompts) == set(EXPECTED_PROMPTS)
    args = {n: [a.name for a in p.arguments or []] for n, p in prompts.items()}
    assert args["qa_full_run"] == ["target_url", "spec_path", "mode"] and args["review_catalog"] == ["run_id"]
    assert args["triage_and_fix"] == ["run_id"] and args["regression_check"] == ["previous_run_id"] and args["explain_run"] == ["run_id"]
    sample = {"qa_full_run": {"target_url": "http://localhost:4000", "spec_path": "spec.md"}, "review_catalog": {"run_id": "r1"},
              "triage_and_fix": {"run_id": "r1"}, "regression_check": {"previous_run_id": "r1"}, "explain_run": {"run_id": "r1"}}
    for name, needles in EXPECTED_PROMPTS.items():
        text = (await server.get_prompt(name, sample[name])).messages[0].content.text
        for n in needles:
            assert n in text, (name, n)
        assert "3 of 3" in text  # the honesty rule is in every prompt that talks about bugs or results
    assert "http://localhost:4000" in (await server.get_prompt("qa_full_run", sample["qa_full_run"])).messages[0].content.text


async def test_server_identity_and_instructions():
    server = create_server()
    assert SERVER_NAME == "kawach-qa" and server.name == "kawach-qa"
    ins = server.instructions
    for needle in ("awaiting_review", "3 of 3", "wait_for_run", "confirm=true", "no separate resume"):
        assert needle in ins, needle
    names = {t.name for t in await server.list_tools()}
    assert {"get_run_summary", "get_bug_fix_context", "save_repro_script", "run_qa_pipeline", "retest_after_fix",
            "compare_runs", "run_project_regression"} <= names


async def test_startup_probe_never_raises_and_reports_status(api, guest):
    api.get(API + "/health").mock(side_effect=httpx.ConnectError("refused"))
    assert (await probe_backend())["status"] == "unreachable"
    api.get(API + "/health").respond(200, json={"status": "active"})
    assert (await probe_backend())["status"] == "active"


async def test_lifespan_starts_and_closes_even_if_backend_is_down(api, guest, caplog):
    import logging
    caplog.set_level(logging.INFO)
    api.get(API + "/health").mock(side_effect=httpx.ConnectError("refused"))
    server = create_server()
    async with server_mod._lifespan(server):
        pass
    assert "health probe: unreachable" in caplog.text and "auth mode guest" in caplog.text
    assert guest._http is None  # client closed on shutdown


async def test_unexpected_exception_becomes_a_concise_error_without_details(caplog):
    @tool(READ)
    async def boom():
        raise RuntimeError("secret-looking detail: hunter2")

    with pytest.raises(KawachError) as ei:
        await boom()
    assert str(ei.value) == "Unexpected error in boom: RuntimeError" and "hunter2" not in str(ei.value)
    assert "Traceback" in caplog.text or "RuntimeError" in caplog.text  # the detail goes to the logs only
