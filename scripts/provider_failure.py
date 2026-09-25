"""Classify retained campaign errors that justify a provider recovery attempt."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PATTERNS = {
    "usage_limit": re.compile(r"usage.?limit|quota|insufficient.?credits", re.I),
    "rate_limit": re.compile(r"rate.?limit|too many requests|\b429\b", re.I),
    "capacity": re.compile(r"selected model is at capacity|model capacity", re.I),
}


def classify_provider_failure(root: Path) -> dict:
    evidence = []
    for path in sorted(root.glob("*/*/error.json")):
        try:
            error = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        message = str(error.get("message") or "")
        categories = [name for name, pattern in PATTERNS.items() if pattern.search(message)]
        if categories:
            evidence.append({
                "case": str(path.relative_to(root).parent),
                "categories": categories,
                "type": error.get("type"),
            })
    return {
        "schema": "starharness.provider_failure.v1",
        "root": str(root.resolve()),
        "recoverable_provider_failure": bool(evidence),
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = classify_provider_failure(args.root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["recoverable_provider_failure"] else 1)


if __name__ == "__main__":
    main()
