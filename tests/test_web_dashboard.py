import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "UI" / "monitor_dashboard.py"
SPEC = importlib.util.spec_from_file_location("starharness_web_dashboard", MODULE_PATH)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


def write_progress(root, method, case, step):
    path = root / method / case / "controller" / "progress.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"step_id": step, "decisions": step // 10}))


def test_task_views_pin_progress_timeline_and_errors_to_selected_task(tmp_path):
    panel = {
        "methods": ["qwenpi_v3", "qwenpi_v3_plus_gpt"],
        "cases": [
            {"task": "task_a", "case_id": "task_a__l0", "layout_id": 0},
            {"task": "task_b", "case_id": "task_b__l0", "layout_id": 0},
        ],
    }
    write_progress(tmp_path, "qwenpi_v3_plus_gpt", "task_a__l0", 40)
    write_progress(tmp_path, "qwenpi_v3_plus_gpt", "task_b__l0", 80)
    errors = [
        {"case": "task_a__l0", "type": "TimeoutError", "recovery": "safe_pre_control_retry"}
    ]
    timeline = [
        {"case": "task_a__l0", "step_id": 40},
        {"case": "task_b__l0", "step_id": 80},
    ]

    views = dashboard.task_views(tmp_path, panel, [], errors, timeline)

    assert views["task_a"]["latest"]["step_id"] == 40
    assert views["task_b"]["latest"]["step_id"] == 80
    assert views["task_a"]["timeline"] == [timeline[0]]
    assert views["task_b"]["timeline"] == [timeline[1]]
    assert views["task_a"]["errors"] == errors
    assert views["task_b"]["errors"] == []


def test_task_scoped_media_does_not_jump_to_another_task(tmp_path):
    frame_a = (
        tmp_path
        / "qwenpi_v3_plus_gpt"
        / "task_a__l0"
        / "controller"
        / "observations"
        / "004"
        / "cam_high.png"
    )
    frame_b = (
        tmp_path
        / "qwenpi_v3_plus_gpt"
        / "task_b__l0"
        / "controller"
        / "observations"
        / "008"
        / "cam_high.png"
    )
    frame_a.parent.mkdir(parents=True)
    frame_b.parent.mkdir(parents=True)
    frame_a.write_bytes(b"a")
    frame_b.write_bytes(b"b")

    media = dashboard.media_info(tmp_path, {"task_a__l0"})

    assert media["case"] == "task_a__l0"
    assert "task_b__l0" not in media["cameras"]["cam_high"]
    assert media["frame_steps"] == ["004"]
    assert media["frame_base"].endswith(
        "/qwenpi_v3_plus_gpt/task_a__l0/controller/observations"
    )


def test_timeline_scans_full_log_before_taking_per_task_limit(tmp_path):
    supervisor = tmp_path.parent / f"{tmp_path.name}-supervisor"
    supervisor.mkdir()
    older = {
        "schema": "robodojo_rollout.codex_decision.v1",
        "episode_id": "old",
        "step_id": 1,
        "simulator_receipt": {
            "record_path": "run/qwenpi_v3_plus_gpt/task_a__l0/decision.json"
        },
    }
    newer = {
        "schema": "robodojo_rollout.codex_decision.v1",
        "episode_id": "new",
        "step_id": 2,
        "simulator_receipt": {
            "record_path": "run/qwenpi_v3_plus_gpt/task_b__l0/decision.json"
        },
    }
    lines = [json.dumps(older)] + ["unrelated"] * 900 + [json.dumps(newer)]
    (supervisor / "campaign.log").write_text("\n".join(lines))

    timeline = dashboard.gpt_decision_timeline(tmp_path)

    assert [item["case"] for item in timeline] == ["task_b__l0", "task_a__l0"]


def test_resumed_campaign_reads_timeline_and_frames_from_source_run(tmp_path):
    active = tmp_path / "active"
    source = tmp_path / "source"
    active.mkdir()
    source.mkdir()
    case_id = "task_a__l0"
    outcomes = [
        {
            "method": "qwenpi_v3_plus_gpt",
            "case_id": case_id,
            "valid_for_success_rate": True,
            "source_run": str(source),
        }
    ]
    frame = (
        source
        / "qwenpi_v3_plus_gpt"
        / case_id
        / "controller"
        / "observations"
        / "012"
        / "cam_high.png"
    )
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"frame")
    supervisor = source.parent / f"{source.name}-supervisor"
    supervisor.mkdir()
    record = {
        "schema": "robodojo_rollout.codex_decision.v1",
        "recorded_at": "2026-09-18T10:00:00Z",
        "step_id": 12,
        "simulator_receipt": {
            "record_path": f"run/qwenpi_v3_plus_gpt/{case_id}/decision.json"
        },
    }
    (supervisor / "campaign.log").write_text(json.dumps(record))

    roots = dashboard.evidence_roots(active, outcomes)
    timeline = dashboard.timeline_across(roots)
    media = dashboard.media_info_across(roots, {case_id}, preferred_case=case_id)

    assert roots == [active.resolve(), source.resolve()]
    assert timeline[0]["case"] == case_id
    assert media["frame_steps"] == ["012"]
    assert media["frame_base"].startswith("/media/1/")


def test_combined_dashboard_adds_direct_campaign_without_changing_pair_count(tmp_path):
    primary = tmp_path / "primary"
    direct = tmp_path / "direct"
    primary.mkdir()
    direct.mkdir()
    case = {"task": "task_a", "case_id": "task_a__l0", "layout_id": 0}
    (primary / "panel.json").write_text(
        json.dumps({"methods": ["qwenpi_v3", "qwenpi_v3_plus_gpt"], "cases": [case]})
    )
    (primary / "outcomes.json").write_text(
        json.dumps(
            [
                {
                    "method": "qwenpi_v3",
                    "case_id": case["case_id"],
                    "valid_for_success_rate": True,
                    "success": False,
                    "score": 0.1,
                }
            ]
        )
    )
    (primary / "comparison.json").write_text(json.dumps({"paired_case_ids": []}))
    (direct / "panel.json").write_text(
        json.dumps({"methods": ["gpt_direct"], "cases": [case]})
    )
    (direct / "outcomes.json").write_text(
        json.dumps(
            [
                {
                    "method": "gpt_direct",
                    "case_id": case["case_id"],
                    "valid_for_success_rate": True,
                    "success": True,
                    "score": 0.8,
                }
            ]
        )
    )

    state = dashboard.collect_combined(primary, [direct])

    assert state["status"]["planned"] == 3
    assert state["status"]["valid"] == 2
    assert state["status"]["paired"] == 0
    assert state["direct"]["successes"] == 1
    assert state["results"]["overall"]["methods"]["gpt_direct"]["score"] == 80
