import numpy as np
import pytest

from starharness.contracts import ContractError, Observation, Proposal


def observation(identifier="episode:0"):
    return Observation(
        observation_id=identifier,
        instruction="build a tower",
        images={"cam_high": object()},
        proprio=np.zeros(14, dtype=np.float32),
        step_id=0,
        remaining_steps=500,
    )


def test_proposal_must_match_observation():
    current = observation()
    proposal = Proposal(
        proposal_id="proposal-1",
        policy_id="qwenpi_v3",
        observation_id="episode:old",
        action_space="dual_arx_x5.abs_qpos.v1",
        actions=np.zeros((50, 14), dtype=np.float32),
        execute_horizon=16,
    )
    proposal.validate(action_dim=14)
    with pytest.raises(ContractError, match="stale"):
        proposal.assert_fresh(current)


def test_proposal_rejects_non_floating_or_non_finite_actions():
    integer = Proposal("p1", "policy", "obs", "joint", np.zeros((2, 14), dtype=np.int64), 1)
    with pytest.raises(ContractError, match="floating-point"):
        integer.validate(action_dim=14)

    values = np.zeros((2, 14), dtype=np.float32)
    values[0, 0] = np.nan
    nonfinite = Proposal("p2", "policy", "obs", "joint", values, 1)
    with pytest.raises(ContractError, match="finite"):
        nonfinite.validate(action_dim=14)
