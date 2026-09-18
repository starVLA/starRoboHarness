"""Bind the approved five-task panel to the upstream frozen native fixtures."""

import argparse
import json
from pathlib import Path

from starroboharness.evaluation import METHODS, panel_digest, validate_panel


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream-panel", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    upstream = json.loads(args.upstream_panel.read_text())
    tasks = [
        "build_tower",
        "put_bottles_into_dustbin",
        "pack_objects_into_box",
        "classify_objects",
        "organize_table",
    ]
    cases = [
        c
        for task in tasks
        for c in upstream["cases"]
        if c["task"] == task and c["rollout_index"] < 5
    ]
    panel = {
        "schema": "starroboharness.panel.v1",
        "benchmark": "RoboDojo",
        "methods": list(METHODS),
        "model": "gpt-6-astra",
        "effort": "xhigh",
        "selection": "User-approved five tasks; first five upstream frozen cases per task",
        "upstream_panel_sha256": upstream["panel_sha256"],
        "cases": cases,
        "student_native_horizon": 16,
        "hybrid_student_horizon": [1, 15],
        "eef_horizon": [1, 5],
        "policy_seed": 0,
        "smoke": "build_tower standard layout 5, excluded from this panel",
    }
    validate_panel(panel)
    if len(cases) != 25:
        raise ValueError("expected exactly 25 cases")
    with args.output.open("x") as stream:
        json.dump(panel, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"panel_sha256": panel_digest(panel), "cases": len(cases)}))


if __name__ == "__main__":
    main()
