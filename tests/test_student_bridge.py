import numpy as np
import pytest

from starroboharness.rollout.student import QwenPIStudent


class Connection:
    metadata = {"action_chunk_size": 50, "default_unnorm_key": "arx_x5"}

    def infer(self, payload):
        self.payload = payload
        actions = np.ones((1, 50, 14), np.float32) * 0.25
        actions[:, :, 6] = -0.1
        actions[:, :, 13] = 1.1
        return {"ok": True, "data": {"actions": actions}}


def test_bridge_preserves_state_raw_actions_and_native_clip(tmp_path):
    connection = Connection()
    bridge = QwenPIStudent(connection, {
        "verified_before_reset": True, "checkpoint": "/checkpoint",
        "checkpoint_sha256": "a" * 64,
    })
    state = np.arange(14, dtype=np.float32)
    observation = {key: np.zeros((480, 640, 3), np.uint8)
                   for key in bridge.adapter.camera_order}
    observation.update(states=state, instruction="original task", remaining_steps=100)
    target = tmp_path / "actions.npz"
    actions, metadata = bridge.infer(observation, target)
    item = connection.payload["examples"][0]
    np.testing.assert_array_equal(item["state"], state[None, :])
    assert item["lang"] == "original task"
    assert all(image.shape == (224, 224, 3) for image in item["image"])
    with np.load(target) as evidence:
        assert evidence["raw_actions"][0, 6] < 0
        np.testing.assert_array_equal(evidence["actions"], actions)
        np.testing.assert_array_equal(actions[:, :6], evidence["raw_actions"][:, :6])
    assert actions[0, 6] == 0 and actions[0, 13] == 1
    assert metadata["inference_index"] == 0
    assert bridge.metadata["backend"] == "StarVLA/PyTorch"
    with pytest.raises(FileExistsError):
        bridge.infer(observation, target)
    assert bridge.index == 1
