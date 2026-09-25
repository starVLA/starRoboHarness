"""Evidence gate and bounded-action validation for hybrid decisions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ContractError

EXECUTION_STATUSES = {"not_started", "progressing", "failed", "uncertain", "recovered"}
INTENT_STATUSES = {"aligned", "misaligned", "uncertain"}
MODES = {"student", "edit", "eef", "stop"}


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be non-empty visible-evidence text")


def _vector(value: Any, length: int, name: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != length:
        raise ContractError(f"{name} must contain {length} numbers")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ContractError(f"{name} must contain {length} finite numbers")
        result.append(float(item))
    return result


def validate_assessment(assessment: Any, *, step_id: int) -> str:
    """Validate outcome and next-intent evidence; return the takeover cause."""

    if not isinstance(assessment, Mapping):
        raise ContractError("outcome and intent assessment is required")
    progress = assessment.get("task_progress")
    if not isinstance(progress, Mapping):
        raise ContractError("task_progress is required")
    for key in ("verified_completed", "remaining"):
        items = progress.get(key)
        invalid = not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip() for item in items
        )
        if invalid:
            raise ContractError(f"task_progress.{key} must be a list of subgoal strings")
    _text(progress.get("currently_attempting"), "task_progress.currently_attempting")
    for key in (
        "current_subgoal",
        "execution_evidence",
        "expected_next_intent",
        "predicted_next_intent",
        "intent_evidence",
    ):
        _text(assessment.get(key), key)
    execution = assessment.get("execution_status")
    intent = assessment.get("intent_status")
    if execution not in EXECUTION_STATUSES:
        raise ContractError("unknown execution_status")
    if intent not in INTENT_STATUSES:
        raise ContractError("unknown intent_status")
    if (step_id == 0) != (execution == "not_started"):
        raise ContractError("not_started is required only before the first control step")
    if execution == "failed" and intent == "misaligned":
        return "both"
    if execution == "failed":
        return "execution_failure"
    if intent == "misaligned":
        return "wrong_intent"
    return "none"


def validate_decision(
    decision: Any,
    *,
    request_id: str,
    step_id: int,
    current_eef: Mapping[str, Mapping[str, Sequence[float]]] | None = None,
    allow_stop: bool = False,
) -> str:
    """Fail closed before execution and return the validated decision mode."""

    if not isinstance(decision, Mapping):
        raise ContractError("decision must be an object")
    if decision.get("request_id") != request_id:
        raise ContractError("decision is stale or belongs to another request")
    _text(decision.get("reason"), "reason")
    mode = decision.get("mode")
    if mode not in MODES:
        raise ContractError("mode must be student, edit, eef, or stop")
    cause = validate_assessment(decision.get("assessment"), step_id=step_id)
    if mode in {"edit", "eef"} and cause == "none":
        raise ContractError("takeover requires observed failure or misaligned next intent")
    if mode == "stop":
        if not allow_stop:
            raise ContractError("stop is disabled when native termination is required")
        return mode
    steps = decision.get("steps")
    cap = 15 if mode == "student" else 5
    if type(steps) is not int or not 1 <= steps <= cap:
        raise ContractError(f"{mode} steps must be within 1..{cap}")
    if mode == "edit":
        for arm in ("left", "right"):
            edit = decision.get("edit", {}).get(arm, {})
            position = _vector(edit.get("delta_position"), 3, f"edit.{arm}.delta_position")
            rotation = _vector(
                edit.get("delta_rotation_vector"), 3, f"edit.{arm}.delta_rotation_vector"
            )
            if math.dist(position, [0.0, 0.0, 0.0]) > 0.05 + 1e-9:
                raise ContractError(f"edit.{arm} translation exceeds 5 cm")
            if math.dist(rotation, [0.0, 0.0, 0.0]) > 0.35 + 1e-9:
                raise ContractError(f"edit.{arm} rotation exceeds 0.35 rad")
            if edit.get("gripper") not in {"keep", "open", "closed"}:
                raise ContractError(f"edit.{arm}.gripper is invalid")
    if mode == "eef":
        if current_eef is None:
            raise ContractError("current_eef is required for EEF validation")
        validate_eef_targets(decision.get("target"), current_eef)
    return mode


def validate_direct_decision(decision, *, request_id, current_eef):
    """Direct control uses the same EEF bounds, without a fictional student gate."""
    if not isinstance(decision, Mapping) or decision.get("request_id") != request_id:
        raise ContractError("direct decision has a stale request_id")
    _text(decision.get("reason"), "reason")
    if decision.get("mode") != "eef":
        raise ContractError("direct control requires EEF mode")
    if type(decision.get("steps")) is not int or not 1 <= decision["steps"] <= 5:
        raise ContractError("direct EEF steps must be within 1..5")
    validate_eef_targets(decision.get("target"), current_eef)
    return "eef"


def validate_eef_targets(targets, current_eef):
    if not isinstance(targets, Mapping) or set(targets) != {"left", "right"}:
        raise ContractError("EEF requires explicit left and right targets")
    for arm in ("left", "right"):
        target = targets[arm]
        position = _vector(target.get("position"), 3, f"target.{arm}.position")
        quaternion = _vector(target.get("quaternion_wxyz"), 4, f"target.{arm}.quaternion_wxyz")
        current_position = _vector(current_eef[arm]["position"], 3, f"current_eef.{arm}.position")
        current_quaternion = _vector(
            current_eef[arm]["quaternion_wxyz"], 4, f"current_eef.{arm}.quaternion_wxyz"
        )
        if math.dist(position, current_position) > 0.05 + 1e-9:
            raise ContractError(f"target.{arm} translation exceeds 5 cm")
        quaternion_norm = math.sqrt(sum(value * value for value in quaternion))
        current_norm = math.sqrt(sum(value * value for value in current_quaternion))
        if abs(quaternion_norm - 1.0) > 1e-4 or abs(current_norm - 1.0) > 1e-4:
            raise ContractError(f"target.{arm} quaternion must be unit length")
        dot = abs(sum(a * b for a, b in zip(quaternion, current_quaternion, strict=True)))
        angle = 2.0 * math.acos(min(1.0, max(0.0, dot)))
        if angle > 0.35 + 1e-9:
            raise ContractError(f"target.{arm} rotation exceeds 0.35 rad")
        if type(target.get("gripper_closed")) is not bool:
            raise ContractError(f"target.{arm}.gripper_closed must be boolean")
