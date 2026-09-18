import json
import subprocess

import pytest

from starroboharness.reasoners import CodexCLIReasoner, ReasonerError


class FakeProcess:
    pid = 12345

    def __init__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.returncode = 0

    def communicate(self, *, input, timeout):
        from pathlib import Path

        output = Path(self.command[self.command.index("--output-last-message") + 1])
        output.write_text('{"request_id":"fresh"}')
        self.kwargs["stdout"].write(
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10},
                }
            )
            + "\n"
        )


def test_exact_identity_and_usage_survive_cli_boundary(tmp_path, monkeypatch):
    launched = []

    def launch(command, **kwargs):
        launched.append(command)
        return FakeProcess(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", launch)
    reasoner = CodexCLIReasoner(tmp_path)
    a = reasoner.infer("one observation", schema={"type": "object"})
    b = reasoner.infer("another observation", schema={"type": "object"})
    assert a["call_dir"] != b["call_dir"]
    assert a["response"] == {"request_id": "fresh"}
    assert a["metadata"]["usage"]["cached_input_tokens"] == 80
    assert a["metadata"]["requested_model"] == "gpt-6-astra"
    assert a["metadata"]["requested_effort"] == "xhigh"
    assert 'model_reasoning_effort="xhigh"' in launched[0]
    assert "--ignore-user-config" in launched[0]
    assert "--ephemeral" in launched[0]


def test_failed_cli_cannot_return_a_stale_decision(tmp_path, monkeypatch):
    class Failed(FakeProcess):
        def communicate(self, **kwargs):
            super().communicate(**kwargs)
            self.returncode = 1

    monkeypatch.setattr(subprocess, "Popen", Failed)
    with pytest.raises(ReasonerError):
        CodexCLIReasoner(tmp_path).infer("observation", schema={"type": "object"})
    receipt = json.loads(next(tmp_path.glob("*/call.json")).read_text())
    assert receipt["status"] == "failed"
    assert receipt["returncode"] == 1


def test_prompt_limit_fails_before_launch(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("CLI should not be invoked")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="bounded-context"):
        CodexCLIReasoner(tmp_path, max_prompt_chars=2).infer("long", schema={"type": "object"})
