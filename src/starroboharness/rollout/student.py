"""QwenPI file-backed proposal boundary for persistent rollout tools."""

import time
from pathlib import Path

import numpy as np

from ..adapters.qwenpi_v3 import QwenPIv3Adapter
from ..contracts import Observation


class QwenPIStudent:
    """Expose upstream's infer(observation, file) protocol with truthful identity.

    This is a data bridge, not a replacement for upstream's pi05-specific
    rollout startup or agent prompts. Runtime identity must be verified by the
    campaign before constructing it. The connection owns transport lifetime.
    """

    def __init__(self, connection, runtime_identity):
        if runtime_identity.get("verified_before_reset") is not True:
            raise ValueError("verified runtime identity is required")
        self.connection = connection
        self.index = 0
        self.raw_actions = None
        self.adapter = QwenPIv3Adapter(
            self._infer, server_metadata=connection.metadata, native_gripper_clip=True
        )
        self.metadata = {
            "checkpoint": runtime_identity["checkpoint"],
            "checkpoint_sha256": runtime_identity["checkpoint_sha256"],
            "config": "QwenPI_v3/arx_x5",
            "backend": "StarVLA/PyTorch",
            "policy_id": "qwenpi_v3",
            "action_horizon": 50,
            "action_dim": 14,
            "runtime_identity": dict(runtime_identity),
        }

    def _infer(self, payload):
        response = self.connection.infer(payload)
        # The adapter validates the envelope, shape and finiteness before use.
        self.raw_actions = response.get("data", {}).get("actions")
        return response

    def infer(self, observation, output):
        path = Path(output)
        if path.exists():
            raise FileExistsError("proposal evidence must not be overwritten")
        before = time.monotonic()
        cameras = self.adapter.camera_order
        obs = Observation(
            observation_id=f"qwenpi-inference-{self.index}",
            instruction=observation["instruction"],
            images={key: _resize_camera(observation[key]) for key in cameras},
            proprio=observation["states"],
            step_id=int(observation.get("step_id", 0)),
            remaining_steps=int(observation["remaining_steps"]),
        )
        proposal = self.adapter.propose(obs)
        with path.open("xb") as stream:
            np.savez_compressed(
                stream, raw_actions=np.asarray(self.raw_actions, np.float32).reshape(50, 14),
                actions=proposal.actions,
                **{key: observation[key] for key in (*cameras, "states")},
            )
        prediction = {
            "prediction_id": proposal.proposal_id,
            "inference_index": self.index,
            "inference_seconds": time.monotonic() - before,
            "policy_id": "qwenpi_v3",
            "proposal_metadata": proposal.metadata,
        }
        self.index += 1
        return proposal.actions, prediction

    def close(self):
        self.connection.close()


def _resize_camera(image):
    """Resize a camera frame without making OpenCV mandatory for contract tests."""

    try:
        import cv2
    except ModuleNotFoundError:
        from PIL import Image

        return np.asarray(Image.fromarray(image).resize((224, 224), Image.Resampling.BOX))
    return cv2.resize(image, (224, 224), interpolation=cv2.INTER_AREA)
