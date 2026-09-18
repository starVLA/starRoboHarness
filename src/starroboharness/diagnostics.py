"""Descriptive proposal diagnostics that never approve an action."""

from __future__ import annotations

from typing import Any

import numpy as np

JOINT_COLUMNS = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12)
OPENING_COLUMNS = (6, 13)


def dual_x5_action_diagnostics(actions: Any) -> dict[str, Any]:
    """Describe a dual-ARX-X5 proposal without clipping or changing it."""

    array = np.asarray(actions)
    result: dict[str, Any] = {
        "schema": "starroboharness.robodojo.action_diagnostics.v1",
        "scope": "Proposal rows only; not a safety, collision, intent, or success verdict.",
        "shape": list(array.shape),
        "finite": None,
        "opening_range": None,
        "max_successive_joint_step_rad": None,
        "status": "unavailable",
    }
    if array.dtype.kind != "f":
        return result
    result["finite"] = bool(np.isfinite(array).all())
    if array.ndim != 2 or array.shape[1] != 14 or len(array) < 2 or not result["finite"]:
        return result
    difference = np.abs(np.diff(array[:, JOINT_COLUMNS], axis=0))
    if not np.isfinite(difference).all():
        return result
    result.update(
        status="computed",
        opening_range=[
            [float(array[:, column].min()), float(array[:, column].max())]
            for column in OPENING_COLUMNS
        ],
        max_successive_joint_step_rad=float(difference.max()),
    )
    return result
