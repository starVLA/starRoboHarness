import numpy as np
import pytest

from starharness.adapters.qwenpi_v3 import QwenPIv3Adapter
from starharness.contracts import ContractError, Observation


def observation():
    return Observation(
        observation_id="episode:7",
        instruction="put all bottles inside the dustbin",
        images={
            "cam_high": np.zeros((224, 224, 3), dtype=np.uint8),
            "cam_left_wrist": np.zeros((224, 224, 3), dtype=np.uint8),
            "cam_right_wrist": np.zeros((224, 224, 3), dtype=np.uint8),
        },
        proprio=np.zeros(14, dtype=np.float32),
        step_id=7,
        remaining_steps=493,
    )


def response(actions):
    return {"ok": True, "data": {"actions": actions}}


def metadata():
    return {
        "action_chunk_size": 50,
        "available_unnorm_keys": ["arx_x5"],
        "default_unnorm_key": "arx_x5",
        "training_obs_image_size": [224, 224],
    }


def test_adapter_preserves_qwenpi_contract():
    actions = np.zeros((1, 50, 14), dtype=np.float32)
    actions[:, :, (6, 13)] = 1.0
    captured = {}

    def infer(request):
        captured.update(request)
        return response(actions)

    proposal = QwenPIv3Adapter(infer, server_metadata=metadata()).propose(observation())
    assert proposal.actions.shape == (50, 14)
    assert proposal.execute_horizon == 16
    assert proposal.action_space == "dual_arx_x5.abs_qpos.v1"
    assert captured["unnorm_key"] == "arx_x5"
    assert len(captured["examples"][0]["image"]) == 3
    assert captured["examples"][0]["state"].shape == (1, 14)
    assert proposal.metadata["diagnostics"]["status"] == "computed"


def test_adapter_rejects_normalized_or_malformed_output():
    bad_gripper = np.zeros((50, 14), dtype=np.float32)
    bad_gripper[:, 6] = -0.01
    with pytest.raises(ContractError, match="gripper"):
        QwenPIv3Adapter(lambda _: response(bad_gripper), server_metadata=metadata()).propose(
            observation()
        )

    wrong_shape = np.zeros((16, 14), dtype=np.float32)
    with pytest.raises(ContractError, match="expected StarVLA actions"):
        QwenPIv3Adapter(lambda _: response(wrong_shape), server_metadata=metadata()).propose(
            observation()
        )


def test_adapter_requires_all_three_cameras():
    current = observation()
    current = Observation(
        current.observation_id,
        current.instruction,
        {"cam_high": current.images["cam_high"]},
        current.proprio,
        current.step_id,
        current.remaining_steps,
    )
    with pytest.raises(ContractError, match="missing cameras"):
        QwenPIv3Adapter(
            lambda _: response(np.zeros((50, 14), dtype=np.float32)),
            server_metadata=metadata(),
        ).propose(current)


def test_adapter_requires_matching_server_metadata():
    bad = metadata()
    bad["available_unnorm_keys"] = ["another_robot"]
    bad["default_unnorm_key"] = "another_robot"
    with pytest.raises(ContractError, match="arx_x5"):
        QwenPIv3Adapter(lambda _: response(np.zeros((50, 14))), server_metadata=bad)
