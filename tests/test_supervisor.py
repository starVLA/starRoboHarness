import json
import os
import signal
import subprocess
import sys
import time

from starharness.rollout.supervisor import supervise


def test_exit_failure_is_preserved_without_retry(tmp_path):
    root = tmp_path / "run"
    assert supervise(root, [sys.executable, "-c", "print('once', flush=True); exit(7)"]) == 7
    assert (root / "campaign.log").read_text() == "once\n"
    receipt = json.loads((root / "exit.json").read_text())
    assert receipt["finished"] and receipt["returncode"] == 7


def test_signal_is_forwarded_and_exit_recorded(tmp_path):
    root = tmp_path / "run"
    parent = subprocess.Popen([
        sys.executable, "-m", "starharness.rollout.supervisor", "--state-dir", str(root),
        "--", sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(60)",
    ])
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            log = root / "campaign.log"
            if log.exists() and "ready" in log.read_text():
                break
            time.sleep(0.05)
        else:
            raise AssertionError("child did not start")
        parent.send_signal(signal.SIGTERM)
        parent.wait(timeout=10)
        receipt = json.loads((root / "exit.json").read_text())
        assert receipt["returncode"] == -signal.SIGTERM
        assert receipt["received_signals"] == [signal.SIGTERM]
        assert not os.path.exists(f"/proc/{receipt['pid']}")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
