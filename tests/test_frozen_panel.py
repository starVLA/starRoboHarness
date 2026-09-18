import json
from collections import Counter
from pathlib import Path

from starroboharness.evaluation import panel_digest, summarize


def test_five_task_panel_is_frozen_and_empty_report_is_pending():
    root = Path(__file__).resolve().parents[1]
    panel = json.loads((root / "configs/evaluation/robodojo_five_tasks_v1.json").read_text())
    assert panel_digest(panel) == "0fc4556a1813ad2ad3c4d65bfd0e5510106d149986a467eed5f24422c4b41d94"
    counts = Counter(case["task"] for case in panel["cases"])
    assert len(counts) == 5 and set(counts.values()) == {5}
    assert all(case["case_id"] != "build_tower__standard__g0__l5" for case in panel["cases"])
    report = summarize(panel, [])
    assert not report["complete"]
    assert report["paired_coverage"] == 0
    assert all(row["success_rate"] is None for row in report["methods"].values())


def test_four_task_starvla_pair_panel_is_frozen():
    root = Path(__file__).resolve().parents[1]
    panel = json.loads((root / "configs/evaluation/robodojo_four_tasks_v1.json").read_text())
    assert panel_digest(panel) == "636d9dfd2be070a3705a23453ebe1b971efae9360b9e90c2a8a26e5ccf3f4d74"
    assert panel["methods"] == ["qwenpi_v3", "qwenpi_v3_plus_gpt"]
    counts = Counter(case["task"] for case in panel["cases"])
    assert counts == {
        "organize_table": 5,
        "classify_objects_by_language": 5,
        "imitate_sorting_sequence": 5,
        "arrange_largest_number": 5,
    }
