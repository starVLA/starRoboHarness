"""Run the StarRoboHarness core contracts without a model or simulator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from starroboharness.contracts import Observation, Proposal
from starroboharness.trace import ChainedJsonlTrace


def main() -> None:
    observation = Observation(
        observation_id="demo:0",
        instruction="move safely to the target",
        images={},
        proprio=np.zeros(7, dtype=np.float32),
        step_id=0,
        remaining_steps=10,
    )
    observation.validate()

    proposal = Proposal(
        proposal_id="demo:proposal:0",
        policy_id="example-policy",
        observation_id=observation.observation_id,
        action_space="example_joint_position",
        actions=np.zeros((1, 7), dtype=np.float32),
        execute_horizon=1,
    )
    proposal.validate(action_dim=7)
    proposal.assert_fresh(observation)

    with tempfile.TemporaryDirectory(prefix="starroboharness-example-") as directory:
        trace = ChainedJsonlTrace(Path(directory) / "trace.jsonl")
        trace.append("observation", {"observation_id": observation.observation_id})
        trace.append("proposal", {"proposal_id": proposal.proposal_id})
        print(f"validated one loop boundary and {len(trace.read_all())} trace events")


if __name__ == "__main__":
    main()
