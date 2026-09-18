import math

import pytest

from starroboharness.contracts import ContractError
from starroboharness.gate import validate_decision


def assessment(execution="progressing", intent="aligned"):
    return {
        "task_progress": {
            "verified_completed": [],
            "currently_attempting": "grasp the next block",
            "remaining": ["place the block"],
        },
        "current_subgoal": "grasp the next block",
        "execution_status": execution,
        "execution_evidence": "The gripper moved toward the visible block.",
        "expected_next_intent": "Approach and grasp the block.",
        "predicted_next_intent": "The trajectory approaches the block.",
        "intent_status": intent,
        "intent_evidence": "The FK endpoint is above the same block.",
    }


def base_decision(mode="student", execution="progressing", intent="aligned"):
    return {
        "request_id": "request-1",
        "mode": mode,
        "steps": 3,
        "reason": "Use the aligned fresh proposal.",
        "assessment": assessment(execution, intent),
    }


def current_eef():
    pose = {"position": [0.0, 0.0, 0.0], "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0]}
    return {"left": pose, "right": pose}


def test_student_is_allowed_when_proposal_is_aligned():
    decision = base_decision()
    assert validate_decision(decision, request_id="request-1", step_id=4) == "student"


def test_uncertainty_does_not_authorize_takeover():
    decision = base_decision("eef", execution="uncertain", intent="uncertain")
    decision["target"] = {
        arm: {
            "position": [0.0, 0.0, 0.0],
            "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
            "gripper_closed": False,
        }
        for arm in ("left", "right")
    }
    with pytest.raises(ContractError, match="takeover"):
        validate_decision(
            decision,
            request_id="request-1",
            step_id=4,
            current_eef=current_eef(),
        )


def test_observed_failure_authorizes_bounded_eef():
    decision = base_decision("eef", execution="failed")
    decision["target"] = {
        arm: {
            "position": [0.03, 0.0, 0.0],
            "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
            "gripper_closed": True,
        }
        for arm in ("left", "right")
    }
    assert (
        validate_decision(
            decision,
            request_id="request-1",
            step_id=4,
            current_eef=current_eef(),
        )
        == "eef"
    )


def test_eef_translation_and_rotation_are_bounded():
    decision = base_decision("eef", execution="failed")
    decision["target"] = {
        arm: {
            "position": [0.051, 0.0, 0.0],
            "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
            "gripper_closed": True,
        }
        for arm in ("left", "right")
    }
    with pytest.raises(ContractError, match="translation"):
        validate_decision(
            decision,
            request_id="request-1",
            step_id=4,
            current_eef=current_eef(),
        )

    half = 0.36 / 2
    for target in decision["target"].values():
        target["position"] = [0.0, 0.0, 0.0]
        target["quaternion_wxyz"] = [math.cos(half), math.sin(half), 0.0, 0.0]
    with pytest.raises(ContractError, match="rotation"):
        validate_decision(
            decision,
            request_id="request-1",
            step_id=4,
            current_eef=current_eef(),
        )


def test_stale_request_and_early_stop_fail_closed():
    decision = base_decision()
    with pytest.raises(ContractError, match="stale"):
        validate_decision(decision, request_id="request-2", step_id=4)

    decision = base_decision("stop")
    with pytest.raises(ContractError, match="native termination"):
        validate_decision(decision, request_id="request-1", step_id=4)
