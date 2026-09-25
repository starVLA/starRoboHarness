"""Freeze a selected RoboDojo task/method panel from an upstream manifest."""

import argparse
import json
from pathlib import Path

from starharness.evaluation import METHODS, panel_digest, validate_panel


def build_panel(upstream, tasks, methods, cases_per_task, start_index=0):
    if not tasks or len(tasks) != len(set(tasks)):
        raise ValueError("tasks must be nonempty and unique")
    if cases_per_task <= 0:
        raise ValueError("cases per task must be positive")
    if start_index < 0:
        raise ValueError("start index must be nonnegative")
    cases = []
    for task in tasks:
        selected = [case for case in upstream["cases"] if case["task"] == task]
        if len(selected) < start_index + cases_per_task:
            raise ValueError(f"{task} has only {len(selected)} upstream cases")
        cases.extend(selected[start_index : start_index + cases_per_task])
    panel = {
        "schema": "starharness.panel.v1",
        "benchmark": "RoboDojo",
        "methods": methods,
        "model": "gpt-6-astra",
        "effort": "xhigh",
        "selection": (
            f"User-approved tasks; upstream frozen cases {start_index}-"
            f"{start_index + cases_per_task - 1} per task"
        ),
        "upstream_panel_sha256": upstream["panel_sha256"],
        "cases": cases,
        "student_native_horizon": 16,
        "hybrid_student_horizon": [1, 15],
        "eef_horizon": [1, 5],
        "policy_seed": 0,
    }
    validate_panel(panel)
    return panel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", action="append", required=True)
    parser.add_argument("--method", action="append", choices=METHODS, required=True)
    parser.add_argument("--cases-per-task", type=int, default=5)
    parser.add_argument("--start-index", type=int, default=0)
    args = parser.parse_args()
    panel = build_panel(
        json.loads(args.upstream_panel.read_text()),
        args.task,
        args.method,
        args.cases_per_task,
        args.start_index,
    )
    with args.output.open("x") as stream:
        json.dump(panel, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"panel_sha256": panel_digest(panel), "cases": len(panel["cases"])}))


if __name__ == "__main__":
    main()
