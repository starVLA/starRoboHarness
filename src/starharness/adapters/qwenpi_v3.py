"""QwenPI_v3 proposal adapter without a StarVLA runtime dependency."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from ..contracts import ContractError, Observation, Proposal
from ..diagnostics import dual_x5_action_diagnostics


class QwenPIv3Adapter:
    """Validate executable proposals returned by an external StarVLA server.

    The injected ``infer`` function owns transport and model execution. It must
    return the existing StarVLA server envelope with actions already
    unnormalized by the checkpoint's ``arx_x5`` statistics.
    """

    policy_id = "qwenpi_v3"
    camera_order = ("cam_high", "cam_left_wrist", "cam_right_wrist")
    action_dim = 14
    action_horizon = 50

    def __init__(
        self,
        infer: Callable[[dict[str, Any]], Mapping[str, Any]],
        *,
        server_metadata: Mapping[str, Any],
        execute_horizon: int = 16,
        native_gripper_clip: bool = False,
    ):
        if type(execute_horizon) is not int or not 1 <= execute_horizon <= self.action_horizon:
            raise ContractError("execute_horizon must be within 1..50")
        self.infer = infer
        self.execute_horizon = execute_horizon
        self.native_gripper_clip = native_gripper_clip
        self.server_metadata = dict(server_metadata)
        self._validate_server_metadata()

    def _validate_server_metadata(self) -> None:
        if self.server_metadata.get("action_chunk_size") != self.action_horizon:
            raise ContractError("StarVLA server action_chunk_size must be 50")
        keys = self.server_metadata.get("available_unnorm_keys", [])
        default = self.server_metadata.get("default_unnorm_key")
        if "arx_x5" not in keys and default != "arx_x5":
            raise ContractError("StarVLA server does not advertise arx_x5 unnormalization")
        image_size = self.server_metadata.get("training_obs_image_size")
        if image_size not in (None, [224, 224], (224, 224)):
            raise ContractError(f"unexpected training image size: {image_size}")

    def _request(self, observation: Observation) -> dict[str, Any]:
        observation.validate()
        missing = [name for name in self.camera_order if name not in observation.images]
        if missing:
            raise ContractError(f"QwenPI_v3 observation is missing cameras: {missing}")
        state = np.asarray(observation.proprio, dtype=np.float32)
        if state.shape != (self.action_dim,):
            raise ContractError(f"QwenPI_v3 requires 14D state, got {state.shape}")
        return {
            "examples": [
                {
                    "lang": observation.instruction,
                    "image": [observation.images[name] for name in self.camera_order],
                    "state": state[None, :],
                }
            ],
            "do_sample": False,
            "use_ddim": True,
            "num_ddim_steps": 10,
            "unnorm_key": "arx_x5",
        }

    @staticmethod
    def _actions(response: Mapping[str, Any], *, native_gripper_clip: bool = False) -> np.ndarray:
        if response.get("ok") is not True:
            error = response.get("error", "unknown error")
            raise ContractError(f"StarVLA inference failed: {error}")
        try:
            actions = np.asarray(response["data"]["actions"], dtype=np.float32)
        except (KeyError, TypeError, ValueError) as error:
            raise ContractError("StarVLA response has no executable actions") from error
        if actions.shape == (1, 50, 14):
            actions = actions[0]
        if actions.shape != (50, 14):
            raise ContractError(
                f"expected StarVLA actions [1,50,14] or [50,14], got {actions.shape}"
            )
        if not np.isfinite(actions).all():
            raise ContractError("QwenPI_v3 proposal contains non-finite values")
        if native_gripper_clip:
            # Match RoboDojo EvalEnv joint-action preprocessing; never alter arm joints.
            actions = actions.copy()
            actions[:, (6, 13)] = np.clip(actions[:, (6, 13)], 0.0, 1.0)
        if np.any((actions[:, (6, 13)] < 0.0) | (actions[:, (6, 13)] > 1.0)):
            raise ContractError("QwenPI_v3 gripper openings must be within [0, 1]")
        return actions

    def propose(self, observation: Observation) -> Proposal:
        response = self.infer(self._request(observation))
        actions = self._actions(response, native_gripper_clip=self.native_gripper_clip)
        raw = np.asarray(response["data"]["actions"], dtype=np.float32).reshape(50, 14)
        proposal = Proposal(
            proposal_id=uuid.uuid4().hex,
            policy_id=self.policy_id,
            observation_id=observation.observation_id,
            action_space="dual_arx_x5.abs_qpos.v1",
            actions=actions,
            execute_horizon=self.execute_horizon,
            metadata={
                "prediction_horizon": self.action_horizon,
                "effective_inference_timesteps": 4,
                "requested_ddim_steps": "10 (ignored by current QwenPI_v3 predict_action path)",
                "camera_order": list(self.camera_order),
                "state_dim": self.action_dim,
                "normalization": "unnormalized_by_server:arx_x5",
                "server_metadata": self.server_metadata,
                "gripper_semantics": "continuous_0_closed_1_open",
                "gripper_postprocess": {
                    "mode": "robodojo_native_clip" if self.native_gripper_clip else "reject",
                    "raw_min": float(raw[:, (6, 13)].min()),
                    "raw_max": float(raw[:, (6, 13)].max()),
                    "changed_entries": int(
                        np.count_nonzero(raw[:, (6, 13)] != actions[:, (6, 13)])
                    ),
                },
                "diagnostics": dual_x5_action_diagnostics(actions),
            },
        )
        proposal.validate(action_dim=self.action_dim)
        proposal.assert_fresh(observation)
        return proposal
