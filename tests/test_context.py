import json

import pytest

from starharness.context import CONTEXT_VERSION, build_context, compact_eef_trajectory
from starharness.contracts import ContractError


def test_context_does_not_leak_reward_or_unbounded_history():
    request = {
        "request_id": "r1",
        "instruction": "stack blocks",
        "step_id": 15,
        "remaining_steps": 100,
        "reward": 0.7,
        "result": {"success": True},
        "hidden_object_positions": [1, 2, 3],
    }
    history = [{"step_id": i, "mode": "student", "reward": 0.2} for i in range(50)]
    context = json.loads(
        build_context(request, memory="First block grasp unverified.", recent_actions=history)
    )
    assert "reward" not in context and "hidden_object_positions" not in context
    assert "result" not in context
    assert [r["step_id"] for r in context["recent_actions"]] == [47, 48, 49]
    assert all("reward" not in r for r in context["recent_actions"])
    assert context["context_version"] == CONTEXT_VERSION
    with pytest.raises(ContractError, match="exceeds limit"):
        build_context(request, max_chars=10)


def test_compact_trajectory_preserves_every_waypoint():
    trajectory = []
    for index in range(50):
        trajectory.append(
            {
                "index": index,
                "left": {
                    "position": [index / 100, 0, 1],
                    "quaternion_wxyz": [1, 0, 0, 0],
                    "gripper_opening": 1,
                },
                "right": {
                    "position": [-index / 100, 0, 1],
                    "quaternion_wxyz": [1, 0, 0, 0],
                    "gripper_opening": 0,
                },
            }
        )
    compact = compact_eef_trajectory(trajectory)
    assert len(compact["rows"]) == 50
    assert compact["rows"][0][0] == 0
    assert compact["rows"][-1][0] == 49
    assert len(json.dumps(compact)) < 12000
