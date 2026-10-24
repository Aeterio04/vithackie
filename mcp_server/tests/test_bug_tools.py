import pytest

from kawach_mcp.errors import KawachError
from kawach_mcp.tools import bugs
from conftest import API, BASE


def replays(*results, ms=1000):
    return [{"index": i, "result": r, "duration_ms": ms + i, "video_url": None} for i, r in enumerate(results, 1)]


R, N = "reproduced", "not_reproduced"
FAKE = [{"index": i, "result": "reproduced", "duration_ms": 1200, "video_url": None} for i in (1, 2, 3)]  # what the live API fabricates


def bug(bid, status, sev="high"):
    # `replays` is deliberately the API's placeholder: tools must ignore it and use the verification record.
    return {"id": bid, "run_id": "run_1", "title": f"Bug {bid}", "severity": sev, "status": status, "replays": FAKE,
            "spec_item_ids": ["S1"], "steps_to_reproduce": ["open", "click"], "expected": "ok", "actual": "boom",
            "repro_script_url": f"/api/v1/runs/run_1/files/scripts/{bid}.spec.ts",
            "evidence": {"screenshots": [f"/api/v1/runs/run_1/files/evidence/{bid}/screenshot.png"],
                         "video_url": f"/api/v1/runs/run_1/files/evidence/{bid}/video.webm", "trace_url": None,
                         "console": ["TypeError: x"]}}


def verification(*hits, ms=400):
    return {"bugId": "x", "attempts": [{"attempt": i, "reproduced": h, "outcome": "failed" if h else "passed",
                                        "durationMs": ms + i} for i, h in enumerate(hits, 1)]}


def mock_verifications(api, **by_id):
    for bid, ver in by_id.items():
        route = api.get(BASE + f"/api/v1/runs/run_1/files/verification/{bid}.json")
        if ver is None:
            route.respond(404, json={"detail": "File not found"})
        else:
            route.respond(200, json=ver)


BUGS = [bug("B_flaky", "flaky", "medium"), bug("B_nr", "not_reproduced", "low"),
        bug("B_conf", "confirmed", "critical"), bug("B_one", "flaky", "low")]
VER = dict(B_flaky=verification(True, False, True), B_nr=verification(False, False, False),
           B_conf=verification(True, True, True), B_one=verification(False, True, False))


async def test_list_bugs_ordering_summary_and_honesty(api, guest):
    api.get(API + "/runs/run_1/bugs").respond(200, json=BUGS)
    mock_verifications(api, **VER)
    r = await bugs.list_bugs("run_1")
    assert [b["id"] for b in r["bugs"]] == ["B_conf", "B_flaky", "B_one", "B_nr"]
    assert [b["verification"] for b in r["bugs"]] == ["3/3 reproduced", "2/3 reproduced", "1/3 reproduced", "0/3 reproduced"]
    assert r["summary"] == {"confirmed": 1, "flaky": 2, "not_reproduced": 1, "unverified": 0, "total": 3}
    assert r["by_severity"] == {"critical": 1}
    assert "2 flaky candidate(s)" in r["honesty_note"] and "NOT counted as confirmed" in r["honesty_note"]
    assert "excluded" in r["honesty_note"]
    assert "replays" not in r["bugs"][0]


async def test_api_fabricated_replays_are_ignored(api, guest):
    """Live finding: the bug API returns 3x 1200ms 'reproduced' replays for anything labelled confirmed."""
    api.get(API + "/runs/run_1/bugs").respond(200, json=[bug("B_liar", "confirmed")])
    mock_verifications(api, B_liar=verification(True, True, False))
    b = (await bugs.list_bugs("run_1"))["bugs"][0]
    assert b["status"] == "flaky" and b["verification"] == "2/3 reproduced" and "treated as flaky" in b["status_note"]


async def test_confirmed_label_without_real_verification_is_unverified(api, guest):
    api.get(API + "/runs/run_1/bugs").respond(200, json=[bug("B_x", "confirmed"), bug("B_y", "confirmed"), bug("B_z", "confirmed")])
    mock_verifications(api, B_x=None, B_y=verification(True), B_z={"attempts": "garbage"})
    r = await bugs.list_bugs("run_1")
    assert all(b["status"] == "unverified" and b["verification"] == "not verified yet" for b in r["bugs"])
    assert r["summary"]["confirmed"] == 0 and r["summary"]["unverified"] == 3 and r["summary"]["total"] == 3
    assert "NOT confirmed" in r["honesty_note"] and r["bugs"][0]["backend_status"] == "confirmed"


async def test_list_bugs_filters(api, guest):
    api.get(API + "/runs/run_1/bugs").respond(200, json=BUGS)
    mock_verifications(api, **VER)
    assert [b["id"] for b in (await bugs.list_bugs("run_1", status="flaky"))["bugs"]] == ["B_flaky", "B_one"]
    assert [b["id"] for b in (await bugs.list_bugs("run_1", severity="critical"))["bugs"]] == ["B_conf"]
    with pytest.raises(KawachError):
        await bugs.list_bugs("run_1", status="confirmed!")


async def test_get_bug_timeline_evidence_and_truncation(api, guest):
    api.get(API + "/bugs/B_conf").respond(200, json=BUGS[2])
    mock_verifications(api, B_conf=verification(True, True, True, ms=1420))
    api.get(BASE + "/api/v1/runs/run_1/files/scripts/B_conf.spec.ts").respond(200, text="x" * 7000)
    r = await bugs.get_bug("B_conf")
    assert r["verification_timeline"] == ["Trial 1: reproduced (failed) 1421ms", "Trial 2: reproduced (failed) 1422ms",
                                          "Trial 3: reproduced (failed) 1423ms", "Verdict: CONFIRMED (3/3 reproduced)"]
    assert r["playwright_code"].endswith("[truncated 1000 chars]") and "full copy" in r["code_note"]
    assert r["evidence"]["screenshots"] == [BASE + "/api/v1/runs/run_1/files/evidence/B_conf/screenshot.png"]
    assert r["evidence"]["video_url"].startswith(BASE) and r["console_errors"] == ["TypeError: x"]
    assert r["steps_to_reproduce"] == ["open", "click"] and r["expected_result"] == "ok" and r["actual_result"] == "boom"
    assert r["testId"] == "B_conf"


async def test_get_bug_flaky_verdict_line_is_not_a_confirmation(api, guest):
    api.get(API + "/bugs/B_flaky").respond(200, json=BUGS[0])
    mock_verifications(api, B_flaky=verification(True, False, True))
    api.get(BASE + "/api/v1/runs/run_1/files/scripts/B_flaky.spec.ts").respond(404, json={"detail": "nf"})
    r = await bugs.get_bug("B_flaky")
    assert r["verification_timeline"][-1] == "Verdict: FLAKY (intermittent, not a confirmed defect) (2/3 reproduced)"
    assert r["status"] == "flaky" and r["playwright_code"] is None


async def test_get_bug_unverified_card(api, guest):
    api.get(API + "/bugs/B_conf").respond(200, json=BUGS[2])
    mock_verifications(api, B_conf=None)
    api.get(BASE + "/api/v1/runs/run_1/files/scripts/B_conf.spec.ts").respond(200, text="code")
    r = await bugs.get_bug("B_conf")
    assert r["status"] == "unverified" and r["verification_timeline"] == ["Verdict: UNVERIFIED (not a confirmed defect)"]


async def test_download_artifact_by_id_and_safety(api, guest, use_client, tmp_path):
    c = use_client(download_dir=tmp_path / "dl")
    api.get(API + "/artifacts/art_1").respond(200, content=b"PNGDATA", headers={"content-type": "image/png"})
    r = await bugs.download_artifact("art_1", filename="../../evil name.png")
    p = tmp_path / "dl" / "artifacts"
    assert r["path"].startswith(str(p.resolve())) and r["size_bytes"] == 7 and r["content_type"] == "image/png"
    assert (p / "evil_name.png").read_bytes() == b"PNGDATA"
    r2 = await bugs.download_artifact("art_1", filename="evil name.png")  # never overwrites
    assert r2["path"].endswith("evil_name_1.png") and c


async def test_download_artifact_urls(api, guest, use_client, tmp_path):
    use_client(download_dir=tmp_path / "dl")
    api.get(API + "/runs/run_1/files/evidence/T1/video.webm").respond(200, content=b"v")
    r = await bugs.download_artifact(BASE + "/api/v1/runs/run_1/files/evidence/T1/video.webm")
    assert r["path"].endswith("video.webm")
    with pytest.raises(KawachError, match="other than the configured backend"):
        await bugs.download_artifact("http://evil.test/a.png")
    with pytest.raises(KawachError, match="Invalid artifact id"):
        await bugs.download_artifact("a b;rm")
