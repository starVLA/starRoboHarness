"""Dependency-light smoke test for policy hosts and simulator hosts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from starroboharness.adapters.qwenpi_v3 import QwenPIv3Adapter
from starroboharness.contracts import Observation
from starroboharness.gate import validate_decision
from starroboharness.trace import ChainedJsonlTrace


def main() -> None:
    images = {
        name: np.zeros((8, 8, 3), dtype=np.uint8)
        for name in ("cam_high", "cam_left_wrist", "cam_right_wrist")
    }
    observation = Observation(
        observation_id="smoke:0",
        instruction="build a tower",
        images=images,
        proprio=np.zeros(14, dtype=np.float32),
        step_id=0,
        remaining_steps=500,
    )
    actions = np.zeros((1, 50, 14), dtype=np.float32)
    actions[:, :, (6, 13)] = 1.0
    proposal = QwenPIv3Adapter(
        lambda request: {"ok": True, "data": {"actions": actions}},
        server_metadata={
            "action_chunk_size": 50,
            "available_unnorm_keys": ["arx_x5"],
            "default_unnorm_key": "arx_x5",
            "training_obs_image_size": [224, 224],
        },
    ).propose(observation)
    decision = {
        "request_id": "request-0",
        "mode": "student",
        "steps": 5,
        "reason": "The fresh proposal approaches the current object.",
        "assessment": {
            "task_progress": {
                "verified_completed": [],
                "currently_attempting": "approach the first block",
                "remaining": ["build the tower"],
            },
            "current_subgoal": "approach the first block",
            "execution_status": "not_started",
            "execution_evidence": "No policy action has executed yet.",
            "expected_next_intent": "Approach the first block.",
            "predicted_next_intent": "The proposal approaches the first block.",
            "intent_status": "aligned",
            "intent_evidence": "The fresh FK path targets the current block.",
        },
    }
    assert validate_decision(decision, request_id="request-0", step_id=0) == "student"
    with tempfile.TemporaryDirectory(prefix="starroboharness-smoke-") as directory:
        trace = ChainedJsonlTrace(Path(directory) / "trace.jsonl")
        trace.append("observation", {"observation_id": observation.observation_id})
        trace.append("proposal", {"proposal_id": proposal.proposal_id})
        trace.append("decision", decision)
        assert len(trace.read_all()) == 3
    print("StarRoboHarness smoke passed: QwenPI_v3 contract, evidence gate, and chained trace")


if __name__ == "__main__":
    main()
