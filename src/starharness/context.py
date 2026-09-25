"""Allowlisted policy context, bounded independently of episode length."""

from __future__ import annotations

import json
from typing import Any

from .contracts import ContractError

PUBLIC_FIELDS = (
    "request_id",
    "task",
    "instruction",
    "step_id",
    "remaining_steps",
    "max_episode_steps",
    "current_state",
    "current_eef",
    "student_eef_trajectory",
    "action_diagnostics",
    "fk_check",
    "previous_execution",
)

CONTEXT_VERSION = "starharness.bounded.v2"


def compact_eef_trajectory(trajectory: list[dict[str, Any]], *, digits: int = 6) -> dict[str, Any]:
    """Keep every FK waypoint in a bounded row encoding.

    The original nested representation is useful as an artifact but needlessly
    expensive in a model prompt.  This encoding preserves all 50 robot-only
    poses and gripper openings while making the columns explicit once.
    """
    if not isinstance(trajectory, list) or not trajectory:
        raise ContractError("student EEF trajectory must be a non-empty list")
    columns = [
        "index",
        "left_xyz",
        "left_quaternion_wxyz",
        "left_gripper_opening",
        "right_xyz",
        "right_quaternion_wxyz",
        "right_gripper_opening",
    ]
    rows = []
    for fallback_index, point in enumerate(trajectory):
        try:
            row = [point.get("index", fallback_index)]
            for arm in ("left", "right"):
                pose = point[arm]
                row.extend(
                    [
                        [round(float(value), digits) for value in pose["position"]],
                        [round(float(value), digits) for value in pose["quaternion_wxyz"]],
                        round(float(pose["gripper_opening"]), digits),
                    ]
                )
        except (KeyError, TypeError, ValueError) as error:
            raise ContractError("invalid student EEF trajectory waypoint") from error
        rows.append(row)
    return {
        "schema": "starharness.eef_trajectory.rows.v1",
        "columns": columns,
        "rows": rows,
    }


def build_context(
    request: dict[str, Any],
    *,
    memory: str = "",
    recent_actions: list[dict[str, Any]] | None = None,
    max_chars: int = 24000,
) -> str:
    """Expose observations and bounded public notes, never outcome/reward fields.

    RGB is attached separately by the caller. Historical action records must
    contain brief explanations, not private chain-of-thought. Unknown fields
    are omitted, including result, reward, object truth, paths, and next_call.
    """
    for key in ("request_id", "instruction", "step_id", "remaining_steps"):
        if key not in request:
            raise ContractError(f"reasoner context requires {key}")
    if not isinstance(memory, str) or len(memory) > 4000:
        raise ContractError("public task memory must be a string of at most 4000 characters")
    actions = []
    for item in (recent_actions or [])[-3:]:
        actions.append(
            {key: item[key] for key in ("step_id", "mode", "steps", "reason") if key in item}
        )
    context = {key: request[key] for key in PUBLIC_FIELDS if key in request}
    context.update(
        context_version=CONTEXT_VERSION,
        public_task_memory=memory,
        recent_actions=actions,
    )
    encoded = json.dumps(context, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded) > max_chars:
        raise ContractError("context exceeds limit; do not silently truncate robot state")
    return encoded
