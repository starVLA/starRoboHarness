import json

from starharness.rollout.development_dashboard import render
from starharness.rollout.monitor import Reader


def _terminal(root, *, success, score, step_id):
    root.mkdir()
    (root / "smoke-result.json").write_text(
        json.dumps(
            {
                "valid_for_success_rate": True,
                "success": success,
                "score": score,
                "metrics": {"step_id": step_id, "decisions": 2},
                "wall_seconds": 60,
            }
        )
    )


def test_development_table_separates_terminal_results_from_unstarted_formal(tmp_path):
    baseline = tmp_path / "baseline"
    hybrid = tmp_path / "hybrid"
    _terminal(baseline, success=False, score=0.1, step_id=1050)
    _terminal(hybrid, success=True, score=1.0, step_id=761)

    entries = [
        ("QwenPI_v3", baseline, tmp_path / "baseline-supervisor"),
        ("Astra + QwenPI", hybrid, tmp_path / "hybrid-supervisor"),
    ]
    screen = render(entries, tmp_path / "formal", 75, Reader())

    assert "FAIL (1 valid)" in screen
    assert "SUCCESS (1 valid)" in screen
    assert "FORMAL FIVE-TASK CAMPAIGN: NOT STARTED | 0/75 valid terminal episodes" in screen
    assert "Do not interpret these rows as the five-task formal success rate" in screen


def test_missing_development_episode_is_not_reported_as_failure(tmp_path):
    entries = [("Astra Direct", tmp_path / "direct", tmp_path / "direct-supervisor")]
    screen = render(entries, tmp_path / "formal", 75, Reader())

    assert "NOT STARTED" in screen
    assert "FAIL" not in screen
