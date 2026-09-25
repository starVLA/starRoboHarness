import json
import subprocess
import sys
from pathlib import Path

from starharness.rollout.monitor import Reader, cell, process_matches_root, render


def test_monitor_retains_last_good_json_on_partial_write(tmp_path):
    path = tmp_path / "live.json"
    path.write_text('{"step": 12}')
    reader = Reader()
    assert reader.read(path)["step"] == 12
    path.write_text('{"step":')
    assert reader.read(path)["step"] == 12
    assert reader.warnings == [str(path)]


def test_monitor_keeps_enriched_progress_during_native_ack_write(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text(json.dumps({
        "step_id": 15,
        "reasoner_calls": 1,
        "usage": {"input_tokens": 500},
    }))
    reader = Reader()
    assert reader.read(path)["reasoner_calls"] == 1

    path.write_text(json.dumps({
        "episode_id": "episode",
        "step_id": 20,
        "student_steps": 20,
        "predictions": 2,
    }))
    progress = reader.read(path)

    assert progress["step_id"] == 20
    assert progress["predictions"] == 2
    assert progress["reasoner_calls"] == 1
    assert progress["usage"] == {"input_tokens": 500}


def test_monitor_accepts_shared_filesystem_alias_for_live_output(tmp_path):
    real = tmp_path / "real-output"
    real.mkdir()
    alias = tmp_path / "output-alias"
    alias.symlink_to(real, target_is_directory=True)
    process = subprocess.Popen([
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        "--output",
        str(alias),
    ])
    try:
        ticks = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        assert process_matches_root(process.pid, real.resolve(), ticks)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_pending_panel_does_not_display_zero_success(tmp_path):
    source = Path(__file__).resolve().parents[1] / "configs/evaluation/robodojo_five_tasks_v1.json"
    (tmp_path / "panel.json").write_text(source.read_text())
    (tmp_path / "outcomes.json").write_text(json.dumps([]))
    screen = render(tmp_path, Reader())
    assert "pending [0/25]" in screen
    assert "valid episodes 0/75" in screen


def test_development_monitor_never_claims_formal_panel_coverage(tmp_path):
    source = Path(__file__).resolve().parents[1] / "configs/evaluation/robodojo_five_tasks_v1.json"
    (tmp_path / "panel.json").write_text(source.read_text())
    (tmp_path / "config.json").write_text('{"smoke_slot": 5}')
    (tmp_path / "smoke-result.json").write_text('{"valid_for_success_rate": false}')
    screen = render(tmp_path, Reader())
    assert "OFF-PANEL DEVELOPMENT" in screen
    assert "valid episodes" not in screen
    assert "0/0=0%" not in screen


def test_running_cell_is_distinct_from_pending_and_terminal_results():
    metric = {"valid": 0, "planned": 5, "successes": 0, "success_rate": None, "score": None}
    assert cell(metric, running=1) == "RUNNING 1/5 [0 valid]"
    metric.update(valid=1, successes=1, success_rate=1.0, score=100.0)
    assert cell(metric, running=1).endswith("+1 run")


def test_stopped_campaign_does_not_show_stale_control_as_active(tmp_path):
    source = Path(__file__).resolve().parents[1] / "configs/evaluation/robodojo_five_tasks_v1.json"
    panel = json.loads(source.read_text())
    (tmp_path / "panel.json").write_text(json.dumps(panel))
    (tmp_path / "campaign-status.json").write_text('{"finished": true}')
    case = tmp_path / "gpt_direct" / panel["cases"][0]["case_id"]
    (case / "controller").mkdir(parents=True)
    (case / "case.json").write_text('{}')
    (case / "controller/progress.json").write_text('{"step_id": 55}')
    screen = render(tmp_path, Reader())
    assert "INTERRUPTED / NO TERMINAL RESULT" in screen
    assert "CONTROL" not in screen
    assert "valid episodes 0/75" in screen


def test_monitor_uses_selected_method_denominator_and_columns(tmp_path):
    source = Path(__file__).resolve().parents[1] / "configs/evaluation/robodojo_five_tasks_v1.json"
    panel = json.loads(source.read_text())
    panel["methods"] = ["qwenpi_v3", "qwenpi_v3_plus_gpt"]
    (tmp_path / "panel.json").write_text(json.dumps(panel))
    (tmp_path / "outcomes.json").write_text("[]")
    screen = render(tmp_path, Reader())
    assert "valid episodes 0/50" in screen
    assert "StarVLA/QwenPI_v3" in screen
    assert "Astra + StarVLA" in screen
    assert "Astra Direct" not in screen
