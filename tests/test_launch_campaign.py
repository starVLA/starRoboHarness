import hashlib
import json

import pytest

from scripts.launch_campaign import probe_codex, runner_command, validate_launch


def write_json(path, value):
    path.write_text(json.dumps(value))
    return path


def fixture(tmp_path):
    python = tmp_path / "python"
    codex = tmp_path / "codex"
    python.write_text("python")
    codex.write_text("codex")
    source = tmp_path / "source"
    source.mkdir()
    (source / "source_manifest.json").write_text("{}")
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    upstream = write_json(
        tmp_path / "upstream.json",
        {"panel_sha256": "upstream", "cases": []},
    )
    panel = write_json(
        tmp_path / "panel.json",
        {
            "benchmark": "RoboDojo",
            "methods": ["qwenpi_v3", "qwenpi_v3_plus_gpt"],
            "model": "gpt-6-astra",
            "effort": "xhigh",
            "upstream_panel_sha256": "upstream",
            "cases": [
                {"case_id": "case", "task": "task", "layout_id": 0, "eval_seed": 0}
            ],
        },
    )
    output = tmp_path / "output"
    config = write_json(
        tmp_path / "config.json",
        {
            "reasoner_backend": "persistent_full_agent_v1",
            "baseline_action_steps": 16,
            "upstream_panel": str(upstream),
            "remote_output": str(output),
            "remote_source": str(source),
            "controller_python": str(python),
            "controller_pythonpath": [str(source), str(dependency)],
            "codex": str(codex),
            "codex_sha256": hashlib.sha256(b"codex").hexdigest(),
            "codex_provider": "openai",
        },
    )
    return config, panel, output


def test_launch_validation_and_command_keep_evidence_paths_explicit(tmp_path):
    config, panel, output = fixture(tmp_path)
    launch = validate_launch(config, panel, output, tmp_path / "supervisor")
    command = runner_command(launch)
    assert "starroboharness.rollout.supervisor" in command
    assert "starroboharness.rollout.campaign" in command
    assert str(output) in command


def test_launch_refuses_to_overwrite_existing_output(tmp_path):
    config, panel, output = fixture(tmp_path)
    output.mkdir()
    with pytest.raises(FileExistsError, match="fresh"):
        validate_launch(config, panel, output, tmp_path / "supervisor")


def test_runner_preserves_venv_interpreter_symlink(tmp_path):
    config_path, panel, output = fixture(tmp_path)
    config = json.loads(config_path.read_text())
    binary = tmp_path / "system-python"
    binary.write_text("python")
    interpreter = tmp_path / "venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(binary)
    config["controller_python"] = str(interpreter)
    write_json(config_path, config)
    launch = validate_launch(config_path, panel, output, tmp_path / "supervisor")
    command = runner_command(launch)
    assert command.count(str(interpreter)) == 2
    assert str(binary) not in command


def test_resume_is_forwarded_to_campaign(tmp_path):
    config, panel, output = fixture(tmp_path)
    launch = validate_launch(config, panel, output, tmp_path / "supervisor")
    launch["resume_from"] = tmp_path / "previous"
    command = runner_command(launch)
    assert command[-2:] == ["--resume-from", str(tmp_path / "previous")]


def test_provider_probe_pins_model_effort_and_provider(tmp_path, monkeypatch):
    config, panel, output = fixture(tmp_path)
    launch = validate_launch(config, panel, output, tmp_path / "supervisor")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["login", "status"]:
            return type("Result", (), {"returncode": 0})()
        stdout = "\n".join((
            json.dumps({"type": "item.completed", "item": {
                "type": "agent_message", "text": "STARROBOHARNESS_PROVIDER_READY"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1}}),
        ))
        return type("Result", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setattr("scripts.launch_campaign.subprocess.run", run)
    identity = probe_codex(launch)
    assert identity["provider"] == "openai"
    assert identity["usage"] == {"input_tokens": 1}
    assert "gpt-6-astra" in calls[-1]
    assert 'model_provider="openai"' in calls[-1]
    assert 'model_reasoning_effort="xhigh"' in calls[-1]
