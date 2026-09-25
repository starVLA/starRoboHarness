import hashlib
import json
from pathlib import Path

import pytest

from starharness.evaluation import panel_digest
from starharness.rollout.campaign import resume_outcomes


def test_resume_preserves_receipts_and_refuses_uncertain_execution(tmp_path):
    root = Path(__file__).resolve().parents[1]
    panel = json.loads((root / "configs/evaluation/robodojo_five_tasks_v1.json").read_text())
    (tmp_path / "panel.json").write_text(json.dumps(panel))
    case = panel["cases"][0]["case_id"]
    directory = tmp_path / "qwenpi_v3" / case
    directory.mkdir(parents=True)
    native = {
        "complete": True,
        "valid_for_success_rate": True,
        "native_success": False,
        "native_score": 0.3,
    }
    (directory / "native-outcome.json").write_text(json.dumps(native))
    row = dict(
        method="qwenpi_v3",
        case_id=case,
        complete=True,
        valid_for_success_rate=True,
        success=False,
        score=0.3,
        termination="native_timeout",
        artifact="native.json",
        panel_sha256=panel_digest(panel),
        native_sha256=hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest(),
    )
    (tmp_path / "outcomes.json").write_text(json.dumps([row]))
    accepted, attempts = resume_outcomes(tmp_path, panel)
    assert len(accepted) == 1 and accepted[0]["success"] is False
    assert attempts == [row]
    row.update(valid_for_success_rate=False, complete=False, termination="infrastructure_error")
    (tmp_path / "outcomes.json").write_text(json.dumps([row]))
    recovered = resume_outcomes(tmp_path, panel)[0]
    assert len(recovered) == 1
    assert recovered[0]["recovered_from_native_receipt"] is True
    assert recovered[0]["termination"] == "native_failure"
    (directory / "native-outcome.json").unlink()
    assert resume_outcomes(tmp_path, panel)[0] == []
    controller = directory / "controller"
    controller.mkdir()
    assert resume_outcomes(tmp_path, panel)[0] == []
    (controller / "run.json").write_text("{}")
    with pytest.raises(ValueError, match="robot control"):
        resume_outcomes(tmp_path, panel)
