import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.fsafe import (plain_filename, safe_dest, safe_extract_zip, sanitize_filename, unique_path)
from kawach_mcp.server import create_server
from kawach_mcp.tools import reports
from conftest import API


def make_zip(entries: dict, symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "../../target")
    return buf.getvalue()


# ---------------- filesystem safety ----------------

@pytest.mark.parametrize("raw,expected", [
    ("report.md", "report.md"), ("../../etc/passwd", "passwd"), ("..\\..\\win.ini", "win.ini"),
    ("my file (1).png", "my_file__1_.png"), (".hidden", "hidden"), ("...", "file"), ("", "file"),
    ("é.txt", "_.txt"), ("a" * 300 + ".md", "a" * 100)])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_safe_dest_stays_inside_and_never_overwrites(tmp_path):
    base = tmp_path / "dl"
    p1 = safe_dest(base, "../../outside", "run 1", filename="../../evil.txt")
    assert p1.resolve().is_relative_to(base.resolve()) and p1.name == "evil.txt"
    p1.write_text("a")
    p2 = safe_dest(base, "../../outside", "run 1", filename="../../evil.txt")
    assert p2.name == "evil_1.txt" and p2 != p1
    assert not (tmp_path / "outside").exists() and not (tmp_path / "evil.txt").exists()


def test_unique_path(tmp_path):
    f = tmp_path / "a.zip"
    assert unique_path(f) == f
    f.write_bytes(b"1")
    (tmp_path / "a_1.zip").write_bytes(b"2")
    assert unique_path(f).name == "a_2.zip"


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b", "/etc/passwd", "C:\\x", ".hidden", "", "a\x00b", ".."])
def test_plain_filename_rejects(name):
    with pytest.raises(KawachError):
        plain_filename(name)


def test_plain_filename_accepts():
    assert plain_filename("report.md") == "report.md" and plain_filename("app_map.json") == "app_map.json"


def test_zip_slip_rejected_and_nothing_written(tmp_path):
    z = tmp_path / "bad.zip"
    z.write_bytes(make_zip({"ok.txt": "fine", "../evil.txt": "pwned"}))
    dest = tmp_path / "out"
    with pytest.raises(KawachError, match="Unsafe path"):
        safe_extract_zip(z, dest)
    assert not (tmp_path / "evil.txt").exists() and not (dest / "ok.txt").exists()


@pytest.mark.parametrize("name", ["/abs/evil.txt", "C:/evil.txt", "sub/../../evil.txt", "..\\evil.txt"])
def test_zip_absolute_and_dotdot_rejected(tmp_path, name):
    z = tmp_path / "bad.zip"
    z.write_bytes(make_zip({name: "x"}))
    with pytest.raises(KawachError, match="Unsafe path"):
        safe_extract_zip(z, tmp_path / "out")


def test_zip_symlink_rejected(tmp_path):
    z = tmp_path / "bad.zip"
    z.write_bytes(make_zip({"a.txt": "x"}, symlink="link"))
    with pytest.raises(KawachError, match="symlink"):
        safe_extract_zip(z, tmp_path / "out")


def test_zip_size_cap_and_normal_extract_without_overwrite(tmp_path):
    z = tmp_path / "ok.zip"
    z.write_bytes(make_zip({"a/b.txt": "hello", "c.txt": "x" * 100}))
    with pytest.raises(KawachError, match="more than"):
        safe_extract_zip(z, tmp_path / "small", max_total=50)
    out = tmp_path / "out"
    assert safe_extract_zip(z, out) == {"files": 2, "bytes": 105}
    assert (out / "a" / "b.txt").read_text() == "hello"
    safe_extract_zip(z, out)  # second extraction must not overwrite
    assert (out / "a" / "b_1.txt").exists() and (out / "a" / "b.txt").read_text() == "hello"


# ---------------- report / export tools ----------------

async def test_get_report_truncation_marker(api, guest):
    api.get(API + "/runs/run_1/files/report.md").respond(200, text="# Report\n" + "x" * 5000)
    r = await reports.get_report("run_1", max_chars=1000)
    assert r["truncated"] is True
    assert r["report"].endswith("[truncated 4009 chars; use export_report_markdown for the full file]")
    full = await reports.get_report("run_1", max_chars=20000)
    assert full["truncated"] is False and "[truncated" not in full["report"]


async def test_get_report_falls_back_to_structured_summary(api, guest):
    api.get(API + "/runs/run_1/files/report.md").respond(404, json={"detail": "File not found"})
    api.get(API + "/runs/run_1/report").respond(200, json={"run": {"id": "run_1", "stage": "running"}, "summary_counts": {"x": 1},
                                                           "verification_funnel": {"confirmed": 0}})
    r = await reports.get_report("run_1")
    assert r["format"] == "json-summary" and "not generated yet" in r["message"]


async def test_get_metrics_summary(api, guest):
    api.get(API + "/runs/run_1/metrics").respond(200, json={
        "wallClockSeconds": 125.4, "tests": {"planned": 10, "approved": 8, "passed": 6, "failed": 2, "errored": 0},
        "bugs": {"candidates": 3, "confirmed": 1, "flaky": 1, "notReproduced": 1},
        "coverage": {"specItems": 10, "specItemsCovered": 7, "pagesInMap": 5, "pagesExercised": 4, "formsInMap": 2, "formsExercised": 1},
        "llm": {"calls": 9, "inputTokens": 1000, "outputTokens": 200, "costUsd": 0.0123}})
    r = await reports.get_metrics("run_1")
    assert r["tests"]["pass_rate_percent"] == 75.0 and r["spec_coverage"]["percent"] == 70.0
    assert r["summary"] == "6/8 tests passed (75.0%), 1 confirmed bug(s), 1 flaky, took 125s, LLM cost $0.0123."
    assert r["llm"]["cost_usd"] == 0.0123 and r["bugs"]["not_reproduced"] == 1


async def test_export_archive_stays_in_download_dir_and_never_overwrites(api, use_client, tmp_path):
    use_client(download_dir=tmp_path / "dl")
    api.get(API + "/runs/run_1/export").respond(200, content=b"ZIP1", headers={"content-type": "application/zip"})
    a = await reports.export_run_archive("run_1")
    b = await reports.export_run_archive("run_1")
    assert Path(a["path"]) == (tmp_path / "dl" / "run_1" / "run_run_1.zip").resolve()
    assert Path(b["path"]).name == "run_run_1_1.zip" and a["size_bytes"] == 4
    for r in (a, b):
        assert Path(r["path"]).resolve().is_relative_to((tmp_path / "dl").resolve())


async def test_export_scripts_extract_is_zip_slip_safe(api, use_client, tmp_path):
    use_client(download_dir=tmp_path / "dl")
    api.get(API + "/runs/run_1/export/scripts").respond(200, content=make_zip({"tests/T01.spec.ts": "ok", "package.json": "{}"}))
    r = await reports.export_playwright_scripts("run_1", extract_to="my scripts")
    assert r["files"] == 2 and (Path(r["extracted_to"]) / "tests" / "T01.spec.ts").read_text() == "ok"
    assert Path(r["extracted_to"]).resolve().is_relative_to((tmp_path / "dl").resolve())
    api.get(API + "/runs/run_2/export/scripts").respond(200, content=make_zip({"../escape.txt": "x"}))
    with pytest.raises(KawachError, match="Unsafe path"):
        await reports.export_playwright_scripts("run_2", extract_to="x")
    assert not (tmp_path / "escape.txt").exists() and not (tmp_path / "dl" / "escape.txt").exists()


async def test_export_catalog_json_and_csv(api, use_client, tmp_path):
    use_client(download_dir=tmp_path / "dl")
    api.get(API + "/runs/run_1/catalog").respond(200, json=[
        {"id": "T01", "title": "Login, with comma", "spec_item_ids": ["S1"], "steps": ["a", "b"], "expected_result": "ok",
         "priority": "high", "review_status": "pending"}])
    j = await reports.export_catalog("run_1", "json")
    assert json.loads(Path(j["path"]).read_text())[0]["status"] == "proposed"
    c = await reports.export_catalog("run_1", "csv")
    lines = Path(c["path"]).read_text().splitlines()
    assert lines[0].startswith("id,title,priority") and '"Login, with comma"' in lines[1]
    with pytest.raises(KawachError):
        await reports.export_catalog("run_1", "xml")


async def test_export_report_markdown(api, use_client, tmp_path):
    use_client(download_dir=tmp_path / "dl")
    api.get(API + "/runs/run_1/files/report.md").respond(200, content=b"# R")
    r = await reports.export_report_markdown("run_1")
    assert Path(r["path"]).read_bytes() == b"# R"


async def test_read_run_file(api, guest):
    api.get(API + "/runs/run_1/files/bugs.json").respond(200, text="y" * 9000)
    r = await reports.read_run_file("run_1", "bugs.json", max_chars=1000)
    assert r["truncated"] and r["content"].endswith("[truncated 8000 chars]") and r["size_chars"] == 9000
    for bad in ("../secrets.json", "evidence/T1/x.png", "/etc/passwd", "..", "C:\\boot.ini"):
        with pytest.raises(KawachError, match="plain file name"):
            await reports.read_run_file("run_1", bad)


# ---------------- registration ----------------

async def test_resources_registered_and_readable(api, guest):
    server = create_server()
    assert [str(r.uri) for r in await server.list_resources()] == ["kawach://projects"]
    templates = sorted(t.uriTemplate for t in await server.list_resource_templates())
    assert templates == ["kawach://runs/{run_id}/app-map", "kawach://runs/{run_id}/bugs",
                         "kawach://runs/{run_id}/catalog", "kawach://runs/{run_id}/report"]
    api.get(API + "/runs/run_1/files/report.md").respond(200, text="# Hello")
    content = list(await server.read_resource("kawach://runs/run_1/report"))[0]
    assert content.content == "# Hello"
    api.get(API + "/projects").respond(200, json=[{"id": "p1", "name": "Shop", "targetUrl": "http://x"}])
    assert "Shop" in list(await server.read_resource("kawach://projects"))[0].content


async def test_every_tool_is_annotated_and_documented():
    tools = await create_server().list_tools()
    names = {t.name for t in tools}
    for expected in ("get_catalog", "get_test", "update_test", "add_test", "review_tests", "approve_all_and_resume",
                     "reject_tests", "get_review_log", "list_bugs", "get_bug", "download_artifact", "wait_for_run",
                     "tail_run_stream", "get_logs", "get_events", "get_execution", "get_app_map", "get_report",
                     "get_metrics", "export_run_archive", "export_playwright_scripts", "export_catalog",
                     "export_report_markdown", "read_run_file"):
        assert expected in names
    for t in tools:
        assert t.description and len(t.description) > 40, t.name
        assert t.annotations is not None and t.annotations.openWorldHint is False, t.name
        assert "ctx" not in t.inputSchema.get("properties", {}), t.name
        if t.name.startswith(("get_", "list_", "tail_", "wait_", "read_")):
            assert t.annotations.readOnlyHint is True, t.name
        if t.name.startswith(("delete_", "cancel_")):
            assert t.annotations.destructiveHint is True and "confirm" in t.inputSchema["properties"], t.name
