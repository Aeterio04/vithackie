"""Offline tests for rehearsal scoreboard calculation and aggregation."""

from kawach_demo.rehearse import BugRehearsalResult


def test_rehearsal_result_aggregation():
    res = BugRehearsalResult(bug_id="bug_1", trials=3)
    assert res.trials == 3
    assert res.proposals_reached == 0
    assert res.edits_valid == 0
    assert res.test_passed_with_fix == 0
    assert res.providers_used == []

    # Simulate 3 trial completions
    res.proposals_reached += 3
    res.edits_valid += 3
    res.test_passed_with_fix += 3
    res.total_duration_sec += 15.0
    res.providers_used.append("Groq")

    avg_sec = res.total_duration_sec / res.trials
    assert avg_sec == 5.0
    assert res.test_passed_with_fix == 3
    assert res.providers_used == ["Groq"]
