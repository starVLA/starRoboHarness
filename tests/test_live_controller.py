from types import SimpleNamespace

import numpy as np
import pytest

from starharness.contracts import ContractError
from starharness.gate import validate_direct_decision
from starharness.rollout.campaign import validate_baseline_cadence
from starharness.rollout.controller import Controller, method_profile


class FakeSim:
    def __init__(self, terminal_after=None):
        self.step = 0
        self.calls = []
        self.terminal_after = terminal_after

    def request(self, op, **kwargs):
        self.calls.append((op, kwargs))
        assert kwargs["step_id"] == self.step
        if op == "chunk_step":
            n = len(kwargs["actions"])
            if self.terminal_after:
                n = min(n, self.terminal_after - self.step)
            self.step += n
            return {
                "step_id": self.step,
                "steps": [
                    {
                        "terminated": self.step == self.terminal_after,
                        "truncated": False,
                        "executed_action": np.zeros(14, dtype=np.float32),
                    }
                    for _ in range(n)
                ],
            }
        raise AssertionError(op)


def test_native_horizon_splits_rpc_without_replanning(tmp_path):
    sim = FakeSim()
    controller = Controller(sim=sim, method="qwenpi_v3", case={}, output=tmp_path / "run")
    proposal = SimpleNamespace(actions=np.arange(700, dtype=np.float32).reshape(50, 14))
    assert not controller.execute({"mode": "student", "steps": 16, "request_id": "r1"}, proposal)
    assert [len(call[1]["actions"]) for call in sim.calls] == [15, 1]
    np.testing.assert_equal(sim.calls[1][1]["actions"], proposal.actions[15:16])
    assert controller.step == 16
    assert controller.previous_execution["executed_steps"] == 16
    assert len(controller.previous_execution["gripper_opening_commands_left_right"]) == 16


def test_method_profiles_do_not_mislabel_baseline_or_direct():
    assert method_profile("qwenpi_v3")["reasoner_session"] == "none"
    assert method_profile("gpt_direct")["student_trajectory"] == "none"
    assert method_profile("qwenpi_v3_plus_gpt")["implementation_variant"] == (
        "compact_ephemeral_reviewer_v2"
    )


def test_chunk15_ablation_is_explicit_and_forbidden_in_formal_campaign():
    profile = method_profile("qwenpi_v3", 15)
    assert profile["baseline_action_steps"] == 15
    assert profile["implementation_variant"].startswith("development_")
    validate_baseline_cadence({"baseline_action_steps": 15}, "qwenpi_v3")
    validate_baseline_cadence({}, None)
    for smoke in (None, "gpt_direct", "qwenpi_v3_plus_gpt"):
        with pytest.raises(ValueError, match="restricted"):
            validate_baseline_cadence({"baseline_action_steps": 15}, smoke)


def test_native_termination_prevents_suffix_execution(tmp_path):
    sim = FakeSim(terminal_after=7)
    controller = Controller(sim=sim, method="qwenpi_v3", case={}, output=tmp_path / "run")
    proposal = SimpleNamespace(actions=np.zeros((50, 14), dtype=np.float32))
    assert controller.execute({"mode": "student", "steps": 16, "request_id": "r1"}, proposal)
    assert len(sim.calls) == 1
    assert controller.step == 7


def test_direct_policy_uses_bounds_without_student_assessment():
    current = {
        arm: {"position": [0, 0, 0], "quaternion_wxyz": [1, 0, 0, 0]} for arm in ("left", "right")
    }
    target = {arm: dict(pose, gripper_closed=False) for arm, pose in current.items()}
    decision = {
        "request_id": "r1",
        "reason": "hold both arms",
        "mode": "eef",
        "steps": 5,
        "target": target,
    }
    assert validate_direct_decision(decision, request_id="r1", current_eef=current) == "eef"
    target["left"]["position"] = [0.051, 0, 0]
    with pytest.raises(ContractError, match="5 cm"):
        validate_direct_decision(decision, request_id="r1", current_eef=current)
