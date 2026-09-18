import json

import pytest

from starroboharness.rollout import campaign


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
