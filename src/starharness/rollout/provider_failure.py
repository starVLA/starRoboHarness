"""Classify retained provider errors without exposing private response bodies."""

from __future__ import annotations

import json
import re
from pathlib import Path

PATTERNS = {
    "usage_limit": re.compile(r"usage.?limit|quota|insufficient.?credits", re.I),
    "rate_limit": re.compile(r"rate.?limit|too many requests|\b429\b", re.I),
    "capacity": re.compile(
        r"selected model is at capacity|model capacity|temporarily at capacity|overloaded",
        re.I,
    ),
}


def failure_message(error) -> str:
    """Extract a bounded, non-secret provider diagnostic from an RPC payload."""
    if isinstance(error, dict):
        value = error.get("message") or error.get("codexErrorInfo") or error.get("error")
    else:
        value = error
    return str(value or "")[:500]


def classify_provider_error(error) -> dict:
    """Classify one live RPC error without treating exhausted quota as retryable.

    Campaign-level isolation may continue after a usage-limit failure, but a
    same-episode restart is only safe/useful for transient capacity or rate
    limiting.  In particular, this prevents spending time replaying a physical
    episode against an account whose credits are exhausted.
    """
    message = failure_message(error)
    categories = [name for name, pattern in PATTERNS.items() if pattern.search(message)]
    return {
        "message": message,
        "categories": categories,
        "recoverable_turn": bool(set(categories) & {"capacity", "rate_limit"}),
    }


def classify_provider_failure(root: Path) -> dict:
    """Return a safe summary of provider failures under a campaign root."""
    root = Path(root)
    evidence = []
    for path in sorted(root.glob("*/*/error.json")):
        try:
            error = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        message = failure_message(error)
        categories = [name for name, pattern in PATTERNS.items() if pattern.search(message)]
        if categories:
            evidence.append(
                {
                    "case": str(path.relative_to(root).parent),
                    "categories": categories,
                    "type": error.get("type"),
                }
            )
    return {
        "schema": "starharness.provider_failure.v1",
        "root": str(root.resolve()),
        "recoverable_provider_failure": bool(evidence),
        "evidence": evidence,
    }
