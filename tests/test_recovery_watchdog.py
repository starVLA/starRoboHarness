from hybrid_rollout.robodojo.robodojo_server.client import recovery_watchdog_state


def response(mode):
    return {"mode": mode, "reason": "test"}


def test_threshold_crossing_is_advisory_and_preserves_distinct_response():
    decision = response("eef")
    decision["target"] = {"left": {"x": 1}, "right": {"x": 2}}

    state = recovery_watchdog_state(8, decision, 8)

    assert state["consecutive_corrections"] == 9
    assert state["exceeded"] is True
    assert state["enforced"] is False
    assert state["last_response"] == decision
    assert "advisory" in state["reason"]


def test_student_execution_resets_advisory_correction_streak():
    state = recovery_watchdog_state(9, response("student"), 8)

    assert state["consecutive_corrections"] == 0
    assert state["exceeded"] is False
    assert state["enforced"] is False
