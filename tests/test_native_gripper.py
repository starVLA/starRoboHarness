import numpy as np

from starharness.adapters.qwenpi_v3 import QwenPIv3Adapter


def test_explicit_native_gripper_clipping_preserves_joints_and_raw_response():
    raw = np.full((1, 50, 14), 1.2, dtype=np.float32)
    raw[..., 6] = -0.04
    response = {"ok": True, "data": {"actions": raw}}
    actions = QwenPIv3Adapter._actions(response, native_gripper_clip=True)
    assert np.all(actions[:, 6] == 0)
    assert np.all(actions[:, 13] == 1)
    assert np.all(actions[:, :6] == np.float32(1.2))
    assert np.all(raw[..., 6] == np.float32(-0.04))
