import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.freeze_task_panel import build_panel
from starroboharness.evaluation import summarize


def upstream():
    source = (
        Path(__file__).resolve().parents[1]
        / "configs/evaluation/robodojo_five_tasks_v1.json"
    )
    original = json.loads(source.read_text())
    original["panel_sha256"] = original["upstream_panel_sha256"]
    return original


def test_task_panel_selects_requested_methods_and_repetitions():
    panel = build_panel(
        upstream(),
        ["build_tower", "organize_table"],
        ["qwenpi_v3", "qwenpi_v3_plus_gpt"],
        3,
    )
    assert panel["methods"] == ["qwenpi_v3", "qwenpi_v3_plus_gpt"]
    assert Counter(case["task"] for case in panel["cases"]) == {
        "build_tower": 3,
        "organize_table": 3,
    }
    assert set(summarize(panel, [])["methods"]) == set(panel["methods"])


def test_task_panel_fails_when_repetitions_are_not_available():
    with pytest.raises(ValueError, match="has only"):
        build_panel(upstream(), ["build_tower"], ["qwenpi_v3"], 99)
