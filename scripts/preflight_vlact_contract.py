#!/usr/bin/env python3
"""Validate the public VLAct RoboDojo contract without loading model weights."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/vlact_robodojo.json"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    errors = []
    if config.get("benchmark") != "RoboDojo":
        errors.append("benchmark must be RoboDojo")
    if config.get("robot_adapter") != "dual_arx_x5":
        errors.append("robot_adapter must be dual_arx_x5")
    if config.get("state_shape") != [1, 14]:
        errors.append("state_shape must be [1, 14]")
    if config.get("action_shape") != [50, 14]:
        errors.append("action_shape must be [50, 14]")
    if config.get("image_size") != [224, 224]:
        errors.append("image_size must be [224, 224]")
    if config.get("execute_horizon", 0) not in range(1, 51):
        errors.append("execute_horizon must be in [1, 50]")
    report = {"schema": "starharness.vlact.contract_preflight.v1", "config": str(args.config), "ok": not errors, "errors": errors}
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
