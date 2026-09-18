import hashlib
import json

from scripts.build_resume_index import build_resume_index
from scripts.provider_failure import classify_provider_failure


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_capacity_is_a_recoverable_provider_failure(tmp_path):
    write_json(
        tmp_path / "hybrid" / "case" / "error.json",
        {"type": "RuntimeError", "message": "Selected model is at capacity."},
    )
    result = classify_provider_failure(tmp_path)
    assert result["recoverable_provider_failure"] is True
    assert result["evidence"][0]["categories"] == ["capacity"]


def test_non_provider_runtime_error_does_not_trigger_recovery(tmp_path):
    write_json(
        tmp_path / "hybrid" / "case" / "error.json",
        {"type": "RuntimeError", "message": "simulator exited early"},
    )
    assert classify_provider_failure(tmp_path)["recoverable_provider_failure"] is False


def test_resume_index_keeps_only_verified_terminal_receipts(tmp_path):
    panel = {"benchmark": "RoboDojo", "methods": ["qwenpi_v3"], "cases": []}
    source = tmp_path / "source"
    write_json(source / "panel.json", panel)
    native = {"complete": True, "valid_for_success_rate": True, "native_score": 0.5}
    write_json(source / "qwenpi_v3" / "valid" / "native-outcome.json", native)
    digest = hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest()
    rows = [
        {
            "method": "qwenpi_v3", "case_id": "valid", "complete": True,
            "valid_for_success_rate": True, "native_sha256": digest,
        },
        {
            "method": "qwenpi_v3", "case_id": "interrupted", "complete": False,
            "valid_for_success_rate": False,
        },
    ]
    write_json(source / "outcomes.json", rows)
    output = tmp_path / "index"
    accepted = build_resume_index([source], output)
    assert [row["case_id"] for row in accepted] == ["valid"]
    assert accepted[0]["source_run"] == str(source.resolve())
    assert json.loads((output / "lineage.json").read_text())["excluded_nonterminal_attempts"] == 1


def test_resume_index_recovers_terminal_receipt_and_records_orphaned_control(tmp_path):
    panel = {
        "benchmark": "RoboDojo", "methods": ["qwenpi_v3"],
        "cases": [{"case_id": "recovered"}, {"case_id": "orphan"}],
    }
    source = tmp_path / "source"
    write_json(source / "panel.json", panel)
    native = {
        "complete": True, "valid_for_success_rate": True,
        "native_success": False, "native_score": 0.25,
        "native_control_steps": 10, "native_step_limit": 10,
    }
    write_json(source / "qwenpi_v3" / "recovered" / "native-outcome.json", native)
    write_json(source / "qwenpi_v3" / "orphan" / "controller" / "run.json", {})
    write_json(source / "outcomes.json", [{
        "method": "qwenpi_v3", "case_id": "recovered", "complete": False,
        "valid_for_success_rate": False, "error_type": "TimeoutExpired",
    }])
    output = tmp_path / "index"
    accepted = build_resume_index([source], output)
    assert accepted[0]["recovered_from_native_receipt"] is True
    assert accepted[0]["termination"] == "native_timeout"
    lineage = json.loads((output / "lineage.json").read_text())
    assert lineage["excluded_nonterminal_attempts"] == 1
    assert lineage["orphaned_controller_attempts"][0]["case_id"] == "orphan"
