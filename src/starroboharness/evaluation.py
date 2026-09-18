"""Paired three-method evaluation without treating missing episodes as failures."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any

from .contracts import ContractError

METHODS = ("qwenpi_v3", "gpt_direct", "qwenpi_v3_plus_gpt")


def efficiency_summary(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate recorded counters only; missing metrics are not zero-cost episodes."""
    recorded = [row["metrics"] for row in outcomes if isinstance(row.get("metrics"), dict)]
    if not recorded:
        return {"episodes_with_metrics": 0}
    totals = {
        key: sum(row.get(key, 0) for row in recorded)
        for key in (
            "reasoner_calls",
            "reasoner_seconds",
            "policy_calls",
            "policy_seconds",
            "control_steps",
            "correction_steps",
            "wall_seconds",
        )
    }
    tokens = {
        key: sum(row.get("usage", {}).get(key, 0) for row in recorded)
        for key in ("input_tokens", "cached_input_tokens", "output_tokens")
    }
    call_units = {}
    for row in recorded:
        if row.get("reasoner_calls", 0):
            unit = row.get("reasoner_call_unit", "ephemeral_inference")
            call_units[unit] = call_units.get(unit, 0) + row["reasoner_calls"]
    return dict(
        episodes_with_metrics=len(recorded),
        reasoner_calls_by_unit=call_units,
        totals=totals,
        tokens=tokens,
        seconds_per_reasoner_call=(
            totals["reasoner_seconds"] / totals["reasoner_calls"]
            if totals["reasoner_calls"] and len(call_units) == 1
            else None
        ),
        correction_fraction=(
            totals["correction_steps"] / totals["control_steps"]
            if totals["control_steps"]
            else None
        ),
        input_cache_fraction=(
            tokens["cached_input_tokens"] / tokens["input_tokens"]
            if tokens["input_tokens"]
            else None
        ),
    )


def panel_digest(panel: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(panel, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def validate_panel(panel: dict[str, Any], *, available_tasks: set[str] | None = None) -> None:
    if panel.get("benchmark") != "RoboDojo":
        raise ContractError("this QwenPI_v3 adapter requires RoboDojo/dual ARX X5")
    methods = panel.get("methods")
    if (
        not isinstance(methods, list)
        or not methods
        or len(methods) != len(set(methods))
        or any(method not in METHODS for method in methods)
    ):
        raise ContractError(f"panel methods must be a nonempty unique subset of {METHODS}")
    if panel.get("model") != "gpt-6-astra" or panel.get("effort") != "xhigh":
        raise ContractError("panel requires the requested gpt-6-astra / xhigh")
    cases = panel.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ContractError("panel requires explicit cases")
    seen = set()
    identities = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ContractError("case must be an object")
        name = case.get("case_id")
        task = case.get("task")
        if not isinstance(name, str) or not name or name in seen:
            raise ContractError("case IDs must be nonempty and unique")
        if not isinstance(task, str) or not task:
            raise ContractError("case task is required")
        if available_tasks is not None and task not in available_tasks:
            raise ContractError(f"{task} is not a registered RoboDojo task")
        for field in ("layout_id", "eval_seed"):
            if type(case.get(field)) is not int or case[field] < 0:
                raise ContractError(f"case {field} must be a nonnegative integer")
        identity = (case.get("runtime_task", task), case["layout_id"], case["eval_seed"])
        if identity in identities:
            raise ContractError("duplicate task/layout/seed under different case IDs")
        identities.add(identity)
        seen.add(name)


def summarize(panel: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Only terminal native outcomes enter SR; compare the common valid cases.

    Scores use native [0, 1] scale here, converted to [0, 100] in reports.
    Duplicate method/case rows are rejected so failed retries cannot disappear.
    Full attempt logs remain external; each row points to its native artifact.
    """
    validate_panel(panel)
    methods = tuple(panel["methods"])
    digest = panel_digest(panel)
    cases = {case["case_id"]: case for case in panel["cases"]}
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in outcomes:
        key = (row.get("method"), row.get("case_id"))
        if key[0] not in methods or key[1] not in cases or key in rows:
            raise ContractError("unknown or duplicate method/case outcome")
        if row.get("panel_sha256") != digest:
            raise ContractError("outcome belongs to a different frozen panel")
        if row.get("valid_for_success_rate") is True:
            if row.get("complete") is not True or row.get("termination") not in {
                "native_success",
                "native_failure",
                "native_timeout",
            }:
                raise ContractError("valid outcome requires native termination")
            if type(row.get("success")) is not bool:
                raise ContractError("success must be a native boolean")
            if row["success"] != (row["termination"] == "native_success"):
                raise ContractError("native termination and success disagree")
            score = row.get("score")
            if type(score) not in {int, float} or not math.isfinite(score) or not 0 <= score <= 1:
                raise ContractError("valid outcome requires native score in [0, 1]")
            if not isinstance(row.get("artifact"), str) or not row["artifact"]:
                raise ContractError("native outcome artifact is required")
        rows[key] = row

    def valid(method, case_id):
        return rows.get((method, case_id), {}).get("valid_for_success_rate") is True

    common = [case_id for case_id in cases if all(valid(m, case_id) for m in methods)]

    def metrics(method, case_ids):
        selected = [rows[method, c] for c in case_ids if valid(method, c)]
        n = len(selected)
        return {
            "valid": n,
            "planned": len(case_ids),
            "successes": sum(r["success"] for r in selected),
            "success_rate": sum(r["success"] for r in selected) / n if n else None,
            "score": 100 * sum(r["score"] for r in selected) / n if n else None,
            "coverage": n / len(case_ids) if case_ids else None,
            "efficiency": efficiency_summary(selected),
            "all_attempts_efficiency": efficiency_summary([
                r for r in outcomes if r["method"] == method and r["case_id"] in case_ids
            ]),
        }

    return {
        "schema": "starroboharness.comparison.v1",
        "panel_sha256": digest,
        "complete": len(common) == len(cases),
        "paired_case_ids": common,
        "paired_coverage": len(common) / len(cases),
        "methods": {m: metrics(m, list(cases)) for m in methods},
        "paired_methods": {m: metrics(m, common) for m in methods},
        "tasks": {
            task: {
                m: metrics(m, [c for c, item in cases.items() if item["task"] == task])
                for m in methods
            }
            for task in sorted({c["task"] for c in cases.values()})
        },
        "status_counts": dict(Counter(row.get("termination", "incomplete") for row in outcomes)),
    }
