import json
from pathlib import Path

import pytest

from starroboharness.rollout.local_campaign import (
    VENDORED_SOURCE,
    build_policy_process,
    build_sim_process,
    preflight,
    resolve_runtime_config,
    select_methods,
)


def executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def base_config(tmp_path):
    starvla = tmp_path / "starvla"
    server = starvla / "deployment/model_server/server_policy.py"
    server.parent.mkdir(parents=True)
    server.write_text("")
    robodojo = tmp_path / "RoboDojo"
    for folder in ("XPolicyLab", "third_party/curobo"):
        (robodojo / folder).mkdir(parents=True)
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"checkpoint")
    base_vlm = tmp_path / "base-vlm"
    base_vlm.mkdir()
    python = executable(tmp_path / "python")
    panel = tmp_path / "upstream-panel.json"
    panel.write_text(json.dumps({"panel_sha256": "abc"}))
    return {
        "starvla_source": str(starvla),
        "starvla_base_vlm": str(base_vlm),
        "checkpoint": str(checkpoint),
        "policy_python": str(python),
        "policy_gpu": 2,
        "policy_port": 6123,
        "robodojo_source": str(robodojo),
        "upstream_panel": str(panel),
        "sim_python": str(python),
        "sim_gpu": 3,
        "sim_port": 19123,
    }


def test_local_policy_process_pins_qwenpi_contract(tmp_path):
    command, environment, cwd = build_policy_process(base_config(tmp_path), tmp_path / "out")
    assert cwd == (tmp_path / "starvla").resolve()
    assert command[-2:] == ["--idle_timeout", "-1"]
    assert "--seed" not in command
    assert command[command.index("--port") + 1] == "6123"
    assert environment["CUDA_VISIBLE_DEVICES"] == "2"
    assert environment["STARVLA_UNNORM_KEY"] == "arx_x5"
    assert environment["STARVLA_EXECUTE_HORIZON"] == "16"
    assert environment["STARVLA_REQUIRED_PI_V3_FORWARD"] == "canonical_interleaved"


def test_local_sim_process_uses_frozen_case_and_separate_gpu(tmp_path):
    config = base_config(tmp_path)
    output = tmp_path / "episode"
    output.mkdir()
    case_file = output / "case.json"
    case_file.write_text("{}")
    case = {"runtime_task": "pack_objects_into_box_random", "eval_seed": 7}
    command, environment, cwd = build_sim_process(config, case, case_file, output)
    assert cwd == output / "sim-service"
    assert command[command.index("--task") + 1] == "pack_objects_into_box_random"
    assert command[command.index("--eval-seed") + 1] == "7"
    assert command[command.index("--case-file") + 1] == str(case_file.resolve())
    assert command[command.index("--output") + 1] == str(output.resolve() / "sim")
    assert environment["CUDA_VISIBLE_DEVICES"] == "3"
    assert environment["ROLLOUT_EVAL_MANIFEST_SHA256"] == "abc"
    assert environment["PYTHONPATH"].split(":")[0] == str(VENDORED_SOURCE)


def test_method_selection_is_canonical_and_deduplicated():
    assert select_methods(None) == (
        "qwenpi_v3",
        "qwenpi_v3_plus_gpt",
        "gpt_direct",
    )
    assert select_methods(["gpt_direct", "qwenpi_v3_plus_gpt", "gpt_direct"]) == (
        "qwenpi_v3_plus_gpt",
        "gpt_direct",
    )


def test_runtime_paths_resolve_from_repository_root(tmp_path):
    absolute = tmp_path / "already-absolute"
    resolved = resolve_runtime_config(
        {
            "checkpoint": "models/checkpoint.pt",
            "robodojo_source": "../RoboDojo",
            "policy_python": str(absolute),
            "unrelated": "unchanged",
        },
        root=tmp_path / "StarRoboHarness",
    )

    assert resolved["checkpoint"] == str(
        (tmp_path / "StarRoboHarness/models/checkpoint.pt").resolve()
    )
    assert resolved["robodojo_source"] == str((tmp_path / "RoboDojo").resolve())
    assert resolved["policy_python"] == str(absolute)
    assert resolved["unrelated"] == "unchanged"


def test_policy_builder_rejects_missing_checkpoint(tmp_path):
    config = base_config(tmp_path)
    Path(config["checkpoint"]).unlink()
    with pytest.raises(ValueError, match="checkpoint is not a file"):
        build_policy_process(config, tmp_path / "out")


def test_preflight_rejects_shared_ports(tmp_path):
    config = base_config(tmp_path)
    config["sim_port"] = config["policy_port"]
    with pytest.raises(ValueError, match="must differ"):
        preflight(config)
