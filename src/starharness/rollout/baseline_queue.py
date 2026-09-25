"""Same-node pure-policy queue with receipt-based acceptance and pre-control retries.

Uses the existing campaign episode and native QwenPI cadence. Only orchestration
changes: readiness/cleanup are local and each attempt has a durable replay boundary.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ..evaluation import panel_digest, validate_panel
from .campaign import Cluster, episode, verify_policy_runtime


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def process_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except FileNotFoundError:
        return None


class LocalForward:
    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


class SameNodeCluster(Cluster):
    """Retain launch specs while eliminating Kubernetes from the control path."""

    def command(self, pod, command, *, stdin=False):
        if pod not in (self.config["sim_pod"], self.config["policy_pod"]):
            raise ValueError("unexpected local service owner")
        return ["bash", "-c", command]

    def read(self, pod, path, *, timeout=30, attempts=1, max_bytes=None):
        with Path(path).open("rb") as stream:
            if max_bytes:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - max_bytes))
            return stream.read().decode()

    def forward(self, pod, local, remote, path):
        if local != remote:
            raise ValueError("same-node transport requires identical local/remote ports")
        stream = Path(path).open("a")
        stream.write("same-node loopback; no Kubernetes tunnel\n")
        stream.flush()
        return LocalForward(), stream


def control_started(directory):
    directory = Path(directory)
    if (directory / "control-started.json").exists():
        return True
    native_path = directory / "native-outcome.json"
    if native_path.exists():
        try:
            if read(native_path).get("native_control_steps", 0) > 0:
                return True
        except (ValueError, TypeError):
            return True
    controller = directory / "controller"
    return controller.exists() and any(controller.iterdir())


def accept_native(directory, case):
    """Validate raw simulator identity, terminal flags and score before acceptance."""
    directory = Path(directory)
    native_path = directory / "native-outcome.json"
    if not native_path.exists():
        return None
    native = read(native_path)
    if not (native.get("complete") is True and native.get("valid_for_success_rate") is True):
        return None
    identity = native.get("evaluation_case", {})
    for key in (
        "case_id",
        "task",
        "runtime_task",
        "variant",
        "eval_seed",
        "layout_id",
        "reset_seed",
        "simulator_initial_seed",
        "policy_rng_seed",
    ):
        if identity.get(key) != case[key]:
            raise ValueError(f"native identity differs: {key}")
    if identity.get("layout_sha256") != case["layout"]["sha256"]:
        raise ValueError("native layout hash differs")
    score = native.get("native_score")
    if type(score) not in (float, int) or not 0 <= score <= 1:
        raise ValueError("invalid native score")
    if type(native.get("native_success")) is not bool:
        raise ValueError("invalid native success flag")
    outcome = read(directory / "outcome.json") if (directory / "outcome.json").exists() else {}
    if (directory / "controller/progress.json").exists():
        outcome["metrics"] = read(directory / "controller/progress.json")
    termination = (
        "native_success"
        if native["native_success"]
        else (
            "native_timeout"
            if native.get("native_control_steps") == native.get("native_step_limit")
            else "native_failure"
        )
    )
    outcome.update(
        method="qwenpi_v3",
        implementation_variant="native_qwenpi_v3_v1",
        case_id=case["case_id"],
        complete=True,
        valid_for_success_rate=True,
        score=score,
        success=native["native_success"],
        termination=termination,
        native_sha256=hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest(),
        native_path=str(native_path),
        source_attempt=str(directory),
    )
    return outcome


def cleanup_services(attempt):
    """Stop only services whose stored PID/start-time still matches this attempt."""
    errors = []
    for config_path in Path(attempt).glob("services/qwenpi_v3/*/*/service_config.json"):
        if not config_path.with_name("process.json").exists():
            errors.append({"receipt": str(config_path), "error": "missing process identity"})
    for receipt_path in Path(attempt).glob("services/qwenpi_v3/*/*/process.json"):
        try:
            receipt = read(receipt_path)
            pid, ticks = receipt["pid"], receipt["start_ticks"]
            if process_identity(pid) != ticks:
                continue
            if os.getpgid(pid) != pid:
                raise RuntimeError("service has unexpected process group")
            os.killpg(pid, signal.SIGTERM)
            deadline = time.monotonic() + 25
            while process_identity(pid) == ticks and time.monotonic() < deadline:
                time.sleep(0.5)
            if process_identity(pid) == ticks:
                os.killpg(pid, signal.SIGKILL)
                time.sleep(1)
            if process_identity(pid) == ticks:
                raise RuntimeError("service remains alive")
        except ProcessLookupError:
            pass
        except Exception as error:
            errors.append({"receipt": str(receipt_path), "error": str(error)})
    return errors


def worker(root, config, panel, case, identity):
    write(root / "runtime-identity.json", identity)
    cfg = dict(config, remote_output=str(root / "services"))
    write(root / "config.json", cfg)
    row = episode(SameNodeCluster(cfg), panel, case, "qwenpi_v3", 0, root)
    write(root / "worker-exit.json", {"finished": True, "valid": row["valid_for_success_rate"]})


def run_queue(root, config, panel):
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "queue.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    validate_panel(panel)
    if panel["methods"] != ["qwenpi_v3"] or config.get("baseline_action_steps") != 16:
        raise ValueError("queue supports only the frozen 16-step pure-policy baseline")
    for name in ("upstream_panel", "checkpoint", "remote_python", "policy_python", "sim_python"):
        if not Path(config[name]).is_file():
            raise ValueError(f"local queue preflight: missing {name}")
    for case in panel["cases"]:
        if not (Path(config["remote_cases"]) / (case["case_id"] + ".json")).is_file():
            raise ValueError("local queue preflight: missing frozen case " + case["case_id"])
    if (root / "panel.json").exists() and panel_digest(read(root / "panel.json")) != panel_digest(
        panel
    ):
        raise ValueError("cannot change a running queue panel")
    write(root / "panel.json", panel)
    write(root / "config.json", config)
    Path(config["xdg_runtime"]).mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = verify_policy_runtime(SameNodeCluster(config), config)
    write(root / "runtime-identity.json", identity)
    outcomes, attempts, quarantined = [], [], []

    def status(current=None, state="running"):
        write(root / "outcomes.json", outcomes)
        write(root / "attempts.json", attempts)
        write(
            root / "status.json",
            {
                "state": state,
                "valid": len(outcomes),
                "planned": len(panel["cases"]),
                "current": current,
                "quarantined": quarantined,
                "heartbeat": time.time(),
                "pid": os.getpid(),
                "start_ticks": process_identity(os.getpid()),
            },
        )

    for case in panel["cases"]:
        case_id = case["case_id"]
        for number in range(1, int(config.get("precontrol_attempts", 3)) + 1):
            attempt = root / "attempts" / case_id / f"attempt-{number:02d}"
            directory = attempt / "qwenpi_v3" / case_id
            attempt.mkdir(parents=True, exist_ok=True)
            receipt_path = attempt / "worker-process.json"
            child = None
            log = None
            if receipt_path.exists():
                receipt = read(receipt_path)
            else:
                if (attempt / "worker-input.json").exists():
                    quarantined.append(case_id)
                    attempts.append(
                        {
                            "case_id": case_id,
                            "attempt": number,
                            "error": "launch identity missing; cannot prove worker stopped",
                        }
                    )
                    break
                write(
                    attempt / "worker-input.json",
                    {"config": config, "panel": panel, "case": case, "identity": identity},
                )
                log = (attempt / "worker.log").open("a")
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "starharness.rollout.baseline_queue",
                        "--worker",
                        str(attempt),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                receipt = {
                    "pid": child.pid,
                    "start_ticks": process_identity(child.pid),
                    "started_at": time.time(),
                }
                write(receipt_path, receipt)
            pid, ticks = receipt["pid"], receipt["start_ticks"]
            watchdog_error = None
            while ticks is not None and process_identity(pid) == ticks:
                status(
                    {
                        "case_id": case_id,
                        "attempt": number,
                        "directory": str(directory),
                        "control_started": control_started(directory),
                    }
                )
                progress = directory / "controller/progress.json"
                last_progress = (
                    progress.stat().st_mtime if progress.exists() else receipt["started_at"]
                )
                limit = 1200 if control_started(directory) else 1500
                if time.time() - last_progress > limit:
                    watchdog_error = (
                        "no_progress_after_control"
                        if control_started(directory)
                        else "precontrol_timeout"
                    )
                    os.killpg(pid, signal.SIGTERM)
                    time.sleep(3)
                    if process_identity(pid) == ticks:
                        os.killpg(pid, signal.SIGKILL)
                    break
                time.sleep(10)
            if child is not None:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    watchdog_error = "worker_cannot_be_reaped"
            if log is not None:
                log.close()
            cleanup = cleanup_services(attempt)
            # Recover a terminal receipt even if worker died while archiving it.
            native_remote = attempt / "services/qwenpi_v3" / case_id / "sim/evaluation_outcome.json"
            if native_remote.exists():
                write(directory / "native-outcome.json", read(native_remote))
            try:
                valid = accept_native(directory, case)
            except (ValueError, TypeError, KeyError) as error:
                valid = None
                cleanup.append({"error": "receipt validation failed: " + str(error)})
            entered = control_started(directory)
            record = {
                "case_id": case_id,
                "attempt": number,
                "path": str(attempt),
                "valid": valid is not None,
                "control_started": entered,
                "watchdog_error": watchdog_error,
                "cleanup_errors": cleanup,
            }
            if (directory / "error.json").exists():
                record["error"] = read(directory / "error.json")
            write(attempt / "adjudication.json", record)
            attempts.append(record)
            if valid:
                outcomes.append(valid)
                break
            if entered or cleanup or (ticks is not None and process_identity(pid) == ticks):
                quarantined.append(case_id)
                break
            time.sleep(10)
        else:
            quarantined.append(case_id)
        status()
    complete = len(outcomes) == len(panel["cases"])
    status(state="complete" if complete else "needs_attention")
    return 0 if complete else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--panel", type=Path)
    args = parser.parse_args()
    if args.worker:
        data = read(args.worker / "worker-input.json")
        worker(args.worker, **data)
        return
    if not all((args.root, args.config, args.panel)):
        parser.error("--root, --config and --panel are required")
    raise SystemExit(run_queue(args.root, read(args.config), read(args.panel)))


if __name__ == "__main__":
    main()
