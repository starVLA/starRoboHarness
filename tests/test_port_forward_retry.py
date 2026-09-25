import json
import subprocess
from types import SimpleNamespace

import pytest

from starharness.rollout import campaign


class FakeProcess:
    def __init__(self, *, stdout, ready=False, returncode=None):
        self._returncode = returncode
        self.terminated = False
        self.killed = False
        if ready:
            stdout.write("Forwarding from 127.0.0.1:29000 -> 19000\n")
            stdout.flush()

    def poll(self):
        return self._returncode

    def terminate(self):
        self.terminated = True
        self._returncode = -15

    def kill(self):
        self.killed = True
        self._returncode = -9

    def wait(self, timeout=None):
        return self._returncode


def cluster():
    return campaign.Cluster(
        {
            "context": "test",
            "namespace": "test",
            "port_forward_attempts": 2,
            "port_forward_startup_seconds": 0.02,
        }
    )


def test_port_forward_retries_before_control_and_records_receipt(tmp_path, monkeypatch):
    processes = []

    def popen(*_args, stdout, **_kwargs):
        process = FakeProcess(stdout=stdout, ready=bool(processes))
        processes.append(process)
        return process

    monkeypatch.setattr(campaign.subprocess, "Popen", popen)
    monkeypatch.setattr(campaign.time, "sleep", lambda _seconds: None)
    path = tmp_path / "policy-forward.log"

    process, log = cluster().forward("policy-pod", 29000, 19000, path)
    log.close()

    assert len(processes) == 2
    assert processes[0].terminated
    assert process is processes[1]
    assert json.loads((tmp_path / "policy-forward.log.attempts.json").read_text()) == [
        {"attempt": 1, "status": "startup_timeout", "returncode": -15},
        {"attempt": 2, "status": "ready"},
    ]


def test_port_forward_exhaustion_is_an_infrastructure_timeout(tmp_path, monkeypatch):
    processes = []

    def popen(*_args, stdout, **_kwargs):
        process = FakeProcess(stdout=stdout)
        processes.append(process)
        return process

    monkeypatch.setattr(campaign.subprocess, "Popen", popen)
    monkeypatch.setattr(campaign.time, "sleep", lambda _seconds: None)

    with pytest.raises(TimeoutError, match="attempt 2/2"):
        cluster().forward("policy-pod", 29001, 19001, tmp_path / "policy-forward.log")

    assert len(processes) == 2
    assert all(process.terminated for process in processes)


def test_remote_read_uses_bounded_python_tail_for_live_logs(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"event":"ready"}')

    monkeypatch.setattr(campaign.subprocess, "run", run)
    remote = campaign.Cluster(
        {
            "context": "test",
            "namespace": "test",
            "remote_python": "/runtime/bin/python",
        }
    )

    assert remote.read(
        "worker", "/runs/case/service.log", max_bytes=1048576
    ) == '{"event":"ready"}'
    shell_command = calls[0][0][-1]
    assert "/runtime/bin/python" in shell_command
    assert "f.seek(max(0,size-n))" in shell_command
    assert shell_command.endswith("/runs/case/service.log 1048576")
    assert "cat " not in shell_command
    assert calls[0][1]["timeout"] == 30


def test_remote_read_keeps_terminal_receipts_exact(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"complete":true}')

    monkeypatch.setattr(campaign.subprocess, "run", run)

    assert cluster().read("worker", "/runs/receipt.json") == '{"complete":true}'
    assert "Path(sys.argv[1]).read_bytes()" in calls[0][0][-1]


def test_remote_read_rejects_non_positive_tail_size():
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        cluster().read("worker", "/runs/case/service.log", max_bytes=0)


def test_remote_read_preserves_timeout_retries(monkeypatch):
    attempts = []

    def run(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise subprocess.TimeoutExpired("kubectl", 7)
        return SimpleNamespace(returncode=0, stdout="receipt")

    monkeypatch.setattr(campaign.subprocess, "run", run)
    monkeypatch.setattr(campaign.time, "sleep", lambda _seconds: None)

    assert cluster().read("worker", "/runs/receipt.json", timeout=7, attempts=2) == "receipt"
    assert len(attempts) == 2
