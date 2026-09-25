"""Paired RoboDojo campaign on two Kubernetes pods and a native CLI controller."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import queue
import shlex
import socket
import subprocess
import threading
import time
import traceback
from pathlib import Path

from ..adapters.qwenpi_v3 import QwenPIv3Adapter
from ..evaluation import METHODS, panel_digest, summarize, validate_panel
from ..reasoners import CodexCLIReasoner
from .controller import Controller, StarVLAConnection, method_profile, save_json
from .provider_failure import classify_provider_failure


def validate_reasoner_backend(config):
    """Never silently substitute the historical compact agent for a typo."""
    backend = config.get("reasoner_backend")
    if backend not in ("persistent_full_agent_v1", "compact"):
        raise ValueError(
            "reasoner_backend must explicitly be persistent_full_agent_v1 or compact"
        )


def validate_baseline_cadence(config, smoke_method):
    steps = config.get("baseline_action_steps", 16)
    if steps not in (15, 16) or (steps != 16 and smoke_method != "qwenpi_v3"):
        raise ValueError("15-step baseline ablation is restricted to QwenPI development smoke")


def check_simulator_startup(log):
    fatal = (
        "Failed to create any GPU devices",
        "CUDA libs are present, but no suitable CUDA GPU was found",
        "libxml2.so.2: cannot open shared object file",
    )
    for message in fatal:
        if message in log:
            raise RuntimeError("Simulator environment preflight failed: " + message)


def close_connections(connections):
    """A failed connection close must not skip the remaining owned cleanup."""
    errors = []
    for connection in connections:
        if connection is not None:
            try:
                connection.close()
            except Exception as error:
                errors.append({"operation": "connection.close", "type": type(error).__name__})
    return errors


def close_log(log, errors):
    """Close a campaign log without masking the primary episode failure.

    The shared object store used by some clusters can report ``EIO`` while a
    remote ``kubectl exec`` stream is being torn down.  Closing a diagnostic
    file must never replace the simulator/policy error with that secondary
    filesystem exception.
    """
    try:
        log.close()
    except OSError as error:
        errors.append({"operation": "log.close", "type": type(error).__name__})


class Cluster:
    def __init__(self, config):
        self.config = config
        self.base = ["kubectl", "--context", config["context"], "-n", config["namespace"]]
        # Concurrent AWS credential/plugin startup can stall otherwise healthy
        # kubectl port-forward commands.  Only tunnel startup is serialized;
        # established forwards and all episode control still run concurrently.
        self.forward_start_lock = threading.Lock()

    def command(self, pod, command, *, stdin=False):
        return (
            self.base
            + ["exec"]
            + (["-i"] if stdin else [])
            + [pod, "-c", "main", "--", "bash", "-lc", command]
        )

    def read(self, pod, path, *, timeout=30, attempts=1, max_bytes=None):
        """Read a remote artifact, retrying transient kubectl transport stalls.

        Some cluster FUSE clients can leave GNU ``cat`` blocked at EOF while
        another process still has the file open for append.  Reading and
        streaming a growing log in full can exhibit the same behavior.  Use a
        bounded tail for readiness logs, while terminal JSON receipts continue
        to use an exact full-file read.
        """
        if max_bytes is not None and max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        interpreter = shlex.quote(self.config.get("remote_python", "python3"))
        if max_bytes is None:
            script = (
                "from pathlib import Path; import sys; sys.stdout.buffer.write("
                "Path(sys.argv[1]).read_bytes())"
            )
            arguments = shlex.quote(str(path))
        else:
            script = (
                "from pathlib import Path; import sys; p=Path(sys.argv[1]); n=int(sys.argv[2]); "
                "f=p.open('rb'); f.seek(0,2); size=f.tell(); f.seek(max(0,size-n)); "
                "sys.stdout.buffer.write(f.read())"
            )
            arguments = f"{shlex.quote(str(path))} {max_bytes}"
        command = f"{interpreter} -c {shlex.quote(script)} {arguments}"
        last_error = None
        for attempt in range(attempts):
            try:
                result = subprocess.run(
                    self.command(pod, command),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as error:
                last_error = error
            else:
                if result.returncode == 0:
                    return result.stdout
                last_error = FileNotFoundError(str(path))
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
        raise last_error

    def capture(self, pod, command, *, timeout=300):
        result = subprocess.run(
            self.command(pod, command), capture_output=True, text=True, timeout=timeout
        )
        if result.returncode:
            raise RuntimeError(f"remote identity command failed on {pod}")
        return result.stdout.strip()

    def start(self, pod, spec, output):
        cfg = self.config
        command = (
            f"PYTHONPATH={shlex.quote(cfg['remote_source'] + '/src')} "
            f"{shlex.quote(cfg['remote_python'])} -m starharness.rollout.service"
        )
        log = Path(output).open("w")
        process = subprocess.Popen(
            self.command(pod, command, stdin=True),
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        process.stdin.write(json.dumps(spec))
        process.stdin.close()
        return process, log

    def stop(self, pod, directory):
        cfg = self.config
        command = (
            f"PYTHONPATH={shlex.quote(cfg['remote_source'] + '/src')} "
            f"{shlex.quote(cfg['remote_python'])} -m starharness.rollout.service "
            f"--stop {shlex.quote(str(Path(directory) / 'process.json'))}"
        )
        result = subprocess.run(
            self.command(pod, command), capture_output=True, text=True, timeout=90
        )
        if result.returncode:
            raise RuntimeError(f"remote service stop failed on {pod}:{directory}")

    def forward(self, pod, local, remote, path):
        with self.forward_start_lock:
            return self._forward_locked(pod, local, remote, path)

    def _forward_locked(self, pod, local, remote, path):
        """Open a local tunnel, retrying only before robot control can begin.

        Kubernetes/API transport occasionally drops the AWS-backed port-forward
        command before it prints its readiness marker.  Retrying here is safe:
        the caller has not opened the simulator RPC connection yet, so no robot
        action can have been acknowledged.  Once this method returns, the
        campaign retains its fail-closed no-replay semantics.
        """
        attempts = int(self.config.get("port_forward_attempts", 3))
        startup_seconds = float(self.config.get("port_forward_startup_seconds", 45))
        if attempts < 1 or attempts > 5:
            raise ValueError("port_forward_attempts must be between 1 and 5")
        if startup_seconds <= 0 or startup_seconds > 180:
            raise ValueError("port_forward_startup_seconds must be in (0, 180]")

        path = Path(path)
        receipts = []
        last_error = None
        for attempt in range(1, attempts + 1):
            # A temporary bind detects collision without consuming the simulator's
            # single owner.  Repeat it because cleanup from a failed attempt must
            # have released the port before a retry is allowed.
            with socket.socket() as check:
                check.bind(("127.0.0.1", local))
            log = path.open("a")
            log.write(f"\n[star-harness port-forward attempt {attempt}/{attempts}]\n")
            log.flush()
            process = subprocess.Popen(
                self.base + ["port-forward", f"pod/{pod}", f"{local}:{remote}"],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + startup_seconds
            status = "startup_timeout"
            try:
                while time.monotonic() < deadline:
                    returncode = process.poll()
                    if returncode is not None:
                        status = "process_exited"
                        last_error = RuntimeError(
                            f"port-forward process exited with code {returncode}: {path}"
                        )
                        break
                    if "Forwarding from" in path.read_text(errors="replace"):
                        status = "ready"
                        receipts.append({"attempt": attempt, "status": "ready"})
                        save_json(path.with_suffix(path.suffix + ".attempts.json"), receipts)
                        return process, log
                    time.sleep(min(0.5, max(startup_seconds / 10, 0.01)))
                else:
                    last_error = TimeoutError(
                        f"port-forward startup timeout on attempt {attempt}/{attempts}: {path}"
                    )
            finally:
                if status != "ready" and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                if status != "ready":
                    try:
                        log.close()
                    except OSError:
                        pass
            receipts.append(
                {
                    "attempt": attempt,
                    "status": status,
                    "returncode": process.poll(),
                }
            )
            save_json(path.with_suffix(path.suffix + ".attempts.json"), receipts)
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))
        raise last_error or TimeoutError(f"port-forward startup failed: {path}")


def episode(cluster, panel, case, method, slot, root):
    cfg = cluster.config
    case_root = root / method / case["case_id"]
    case_root.mkdir(parents=True, exist_ok=False)
    remote = Path(cfg["remote_output"]) / method / case["case_id"]
    selected = {"identity": None, "case": case}
    from hybrid_rollout.robodojo.evaluation import case_identity

    upstream = json.loads(Path(cfg["upstream_panel"]).read_text())
    selected["identity"] = case_identity(upstream, case)
    # All case files are staged once before launch; hash-checked by the upstream simulator.
    sim_port, policy_port, local_sim, local_policy = case_ports(cfg, slot)
    services, forwards = [], []
    connection = sim = None
    start = time.monotonic()
    outcome = {
        "method": method,
        "implementation_variant": method_profile(
            method, cfg.get("baseline_action_steps", 16))["implementation_variant"],
        "case_id": case["case_id"],
        "panel_sha256": panel_digest(panel),
        "complete": False,
        "valid_for_success_rate": False,
        "termination": "infrastructure_error",
        "artifact": str(remote / "sim" / "evaluation_outcome.json"),
    }
    save_json(case_root / "case.json", selected)
    save_json(case_root / "outcome.json", outcome)
    try:
        learned = method != "gpt_direct"
        if learned:
            policy_env = {
                "CUDA_VISIBLE_DEVICES": str(slot),
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "NO_ALBUMENTATIONS_UPDATE": "1",
                "PYTHONPATH": cfg["starvla_source"],
                "PYTHONUNBUFFERED": "1",
            }
            spec = {
                "output": str(remote / "policy"),
                "cwd": cfg["starvla_source"],
                "environment": policy_env,
                "command": [
                    cfg["policy_python"],
                    "deployment/model_server/server_policy.py",
                    "--ckpt_path",
                    cfg["checkpoint"],
                    "--port",
                    str(policy_port),
                    "--use_bf16",
                    "--seed",
                    "0",
                    "--idle_timeout",
                    "-1",
                ],
            }
            process, log = cluster.start(cfg["policy_pod"], spec, case_root / "policy-launch.log")
            services.append((cfg["policy_pod"], remote / "policy", process, log))
        runtime = cfg["graphics_runtime"]
        env = {
            "CUDA_VISIBLE_DEVICES": str(slot),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": ":".join(
                [
                    cfg["remote_source"] + "/src",
                    cfg["robodojo_source"],
                    cfg["robodojo_source"] + "/XPolicyLab",
                    cfg["robodojo_source"] + "/third_party/curobo",
                    *cfg.get("sim_extra_pythonpath", []),
                ]
            ),
            "LD_LIBRARY_PATH": runtime,
            "VK_ICD_FILENAMES": runtime + "/nvidia_icd.json",
            "__EGL_VENDOR_LIBRARY_FILENAMES": runtime + "/10_nvidia.json",
            "OMNI_KIT_ACCEPT_EULA": "Y",
            "XDG_RUNTIME_DIR": cfg["xdg_runtime"],
            "ROLLOUT_EVAL_MANIFEST_SHA256": upstream["panel_sha256"],
        }
        spec = {
            "output": str(remote / "sim-service"),
            "cwd": str(remote / "sim-service"),
            "environment": env,
            "command": [
                cfg["sim_python"],
                "-m",
                "hybrid_rollout.robodojo.robodojo_server.server",
                "--task",
                case["runtime_task"],
                "--eval-seed",
                str(case["eval_seed"]),
                "--output",
                str(remote / "sim"),
                "--port",
                str(sim_port),
                "--eval-manifest",
                cfg["remote_source"]
                + "/src/hybrid_rollout/robodojo/eval_panels/"
                + Path(cfg["upstream_panel"]).name,
                "--case-file",
                str(Path(cfg["remote_cases"]) / (case["case_id"] + ".json")),
            ],
        }
        process, log = cluster.start(cfg["sim_pod"], spec, case_root / "sim-launch.log")
        services.append((cfg["sim_pod"], remote / "sim-service", process, log))
        deadline = time.monotonic() + 900
        sim_ready = policy_ready = False
        while time.monotonic() < deadline:
            for pod, directory, process, _log in services:
                if process.poll() is not None:
                    raise RuntimeError(f"remote service exited early: {pod}:{directory}")
            try:
                sim_log = cluster.read(
                    cfg["sim_pod"], remote / "sim-service/service.log", max_bytes=1_048_576
                )
                check_simulator_startup(sim_log)
                sim_ready = '"event": "ready"' in sim_log
                policy_ready = not learned or "server listening" in cluster.read(
                    cfg["policy_pod"], remote / "policy/service.log", max_bytes=1_048_576
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            if sim_ready and policy_ready:
                break
            time.sleep(5)
        if not sim_ready or not policy_ready:
            raise TimeoutError("services were not ready in 900 seconds")
        forwards.append(
            cluster.forward(cfg["sim_pod"], local_sim, sim_port, case_root / "sim-forward.log")
        )
        adapter = None
        if learned:
            forwards.append(
                cluster.forward(
                    cfg["policy_pod"], local_policy, policy_port, case_root / "policy-forward.log"
                )
            )
            connection = StarVLAConnection(local_policy, case_root / "raw-policy")
            save_json(case_root / "policy-metadata.json", connection.metadata)
            adapter = QwenPIv3Adapter(
                connection.infer, server_metadata=connection.metadata, native_gripper_clip=True
            )
        persistent = (
            cfg.get("reasoner_backend") == "persistent_full_agent_v1"
            and method != "qwenpi_v3"
        )
        # Conservative replay boundary: persist before any controller can reset/act.
        save_json(case_root / "control-started.json", {"time": time.time(), "method": method})
        if persistent:
            from .persistent_episode import run_persistent

            outcome["implementation_variant"] = "persistent_full_agent_v1"
            result = run_persistent(
                root=case_root, method=method, case=case, config=cfg, connection=connection,
                sim_port=local_sim,
                runtime_identity=json.loads((root / "runtime-identity.json").read_text()),
            )
        else:
            result = run_compact(case_root, cfg, method, case, adapter, local_sim)
        native = json.loads(cluster.read(
            cfg["sim_pod"], remote / "sim/evaluation_outcome.json", timeout=90, attempts=3
        ))
        save_json(case_root / "native-outcome.json", native)
        outcome.update(
            complete=native["complete"],
            valid_for_success_rate=native["valid_for_success_rate"],
            success=native["native_success"],
            score=native["native_score"],
            native_sha256=hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest(),
            termination=native.get("reason", "incomplete")
            if not native["valid_for_success_rate"]
            else "native_success"
            if native["native_success"]
            else "native_timeout"
            if result["truncated"]
            else "native_failure",
            metrics=json.loads((case_root / "controller/progress.json").read_text()),
        )
    except BaseException as error:
        save_json(
            case_root / "error.json",
            {
                "type": type(error).__name__,
                "message": str(error) or None,
                "traceback": traceback.format_exc(),
            },
        )
        outcome["error_type"] = type(error).__name__
    finally:
        cleanup_errors = close_connections((connection, sim))
        for pod, directory, process, log in services:
            try:
                # Preserve native error outcomes too, without changing their denominator status.
                if pod == cfg["sim_pod"]:
                    native = json.loads(cluster.read(
                        pod, remote / "sim/evaluation_outcome.json", timeout=90, attempts=3
                    ))
                    save_json(case_root / "native-outcome.json", native)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                cleanup_errors.append({"operation": "native_receipt.read", "pod": pod,
                                       "directory": str(directory), "type": type(error).__name__})
            try:
                cluster.stop(pod, directory)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                cleanup_errors.append({"operation": "service.stop", "pod": pod,
                                       "directory": str(directory), "type": type(error).__name__})
            try:
                process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                process.terminate()
            close_log(log, cleanup_errors)
        for process, log in forwards:
            try:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as error:
                cleanup_errors.append({"operation": "forward.stop", "type": type(error).__name__})
            finally:
                close_log(log, cleanup_errors)
        if cleanup_errors:
            save_json(case_root / "cleanup-errors.json", cleanup_errors)
        outcome["wall_seconds"] = time.monotonic() - start
        progress_path = case_root / "controller/progress.json"
        if progress_path.exists():
            try:
                metrics = json.loads(progress_path.read_text())
                usage_path = case_root / "reasoner/usage.json"
                if usage_path.exists():
                    usage = json.loads(usage_path.read_text())
                    metrics["usage"] = {
                        "input_tokens": usage.get("inputTokens", 0),
                        "cached_input_tokens": usage.get("cachedInputTokens", 0),
                        "output_tokens": usage.get("outputTokens", 0),
                    }
                    metrics["usage_accounting"] = "last_reported_async_usage_not_final_billing"
                outcome["metrics"] = metrics
            except (OSError, ValueError):
                pass
        save_json(case_root / "outcome.json", outcome)
    return outcome


def run_compact(case_root, cfg, method, case, adapter, local_sim):
    from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient

    reasoner = (
        None
        if method == "qwenpi_v3"
        else CodexCLIReasoner(
            case_root / "reasoner", executable=cfg["codex"], timeout_seconds=300
        )
    )
    sim = RPCClient("127.0.0.1", local_sim, timeout=600)
    try:
        controller = Controller(
            sim=sim,
            method=method,
            case=case,
            output=case_root / "controller",
            policy=adapter,
            reasoner=reasoner,
            smoke_decisions=cfg.get("smoke_decisions", 0),
            baseline_action_steps=cfg.get("baseline_action_steps", 16),
        )
        return controller.run()
    finally:
        sim.close()


def verify_policy_runtime(cluster, config):
    """Prove the checkpoint and compatibility patch before any reset occurs."""
    required = (
        "policy_pod",
        "checkpoint",
        "checkpoint_sha256",
        "starvla_source",
        "starvla_commit",
        "starvla_normalization_patch_sha256",
    )
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError("runtime identity is missing: " + ", ".join(missing))
    pod = config["policy_pod"]
    checkpoint = shlex.quote(config["checkpoint"])
    source = shlex.quote(config["starvla_source"])
    commit = cluster.capture(pod, f"git -C {source} rev-parse HEAD").strip()
    if commit != config["starvla_commit"]:
        raise ValueError("StarVLA commit differs from the frozen runtime config")
    checkpoint_sha = cluster.capture(pod, f"sha256sum -- {checkpoint}").split()[0]
    patch_command = (
        f"git -C {source} diff HEAD -- "
        "deployment/model_server/policy_norm_processor.py "
        "deployment/model_server/policy_wrapper.py | sha256sum"
    )
    patch_sha = cluster.capture(pod, patch_command).split()[0]
    if checkpoint_sha != config["checkpoint_sha256"]:
        raise ValueError("checkpoint SHA-256 differs from the frozen runtime config")
    if patch_sha != config["starvla_normalization_patch_sha256"]:
        raise ValueError("StarVLA normalization patch differs from the frozen runtime config")
    return {
        "schema": "starharness.runtime_identity.v1",
        "policy_pod": pod,
        "checkpoint": config["checkpoint"],
        "checkpoint_sha256": checkpoint_sha,
        "starvla_source": config["starvla_source"],
        "starvla_commit": commit,
        "starvla_normalization_patch_sha256": patch_sha,
        "verified_before_reset": True,
    }


def resume_outcomes(root, panel):
    """Reuse native results, never replay a case after uncertain robot execution."""
    previous = json.loads((root / "panel.json").read_text())
    if panel_digest(previous) != panel_digest(panel):
        raise ValueError("resume panel differs from frozen panel")
    rows = json.loads((root / "outcomes.json").read_text())
    summarize(panel, rows)
    accepted = []
    for row in rows:
        directory = root / row["method"] / row["case_id"]
        origin = Path(row.get("source_run", root))
        native_path = origin / row["method"] / row["case_id"] / "native-outcome.json"
        native = json.loads(native_path.read_text()) if native_path.is_file() else None
        if row["valid_for_success_rate"]:
            digest = hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest()
            if digest != row["native_sha256"]:
                raise ValueError("resume native receipt digest mismatch")
            accepted.append(dict(row, source_run=str(origin.resolve())))
        elif native and native.get("complete") and native.get("valid_for_success_rate"):
            digest = hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest()
            steps = native.get("native_control_steps")
            limit = native.get("native_step_limit")
            termination = (
                "native_success" if native.get("native_success") else
                "native_timeout" if steps is not None and steps == limit else
                "native_failure"
            )
            recovered = dict(
                row,
                complete=True,
                valid_for_success_rate=True,
                success=native.get("native_success"),
                score=native.get("native_score"),
                termination=termination,
                native_sha256=digest,
                recovered_from_native_receipt=True,
                source_run=str(origin.resolve()),
            )
            recovered.pop("error_type", None)
            accepted.append(recovered)
        elif any(
            (directory / "controller" / name).exists()
            for name in ("run.json", "progress.json", "history.json")
        ):
            raise ValueError("cannot automatically retry a case that entered robot control")
    return accepted, rows


def finish_campaign(root, panel, outcomes, *, stopped):
    """Distinguish completed native failures from interrupted campaigns."""
    methods = panel.get("methods", list(METHODS))
    expected = {(method, case["case_id"]) for case in panel["cases"] for method in methods}
    valid = {
        (row["method"], row["case_id"])
        for row in outcomes
        if row.get("valid_for_success_rate") and row.get("complete")
    }
    complete = not stopped and valid == expected and len(outcomes) == len(expected)
    save_json(
        root / "campaign-status.json",
        {"finished": True, "complete": complete, "episodes": len(outcomes)},
    )
    if not complete:
        raise SystemExit(2)


def cases_requiring_work(panel, completed):
    """Return each unfinished case once; its selected methods stay paired on one slot."""
    return [
        case
        for case in panel["cases"]
        if any((method, case["case_id"]) not in completed for method in panel["methods"])
    ]


def may_continue_after_invalid(config: dict, root: Path, row: dict) -> bool:
    """Isolate an explicitly classified provider-quota failure per case.

    This never retries a physical-control attempt: the invalid row remains in
    ``outcomes.json`` and is excluded from SR/Score.  Generic simulator and
    controller failures remain fail-closed unless separately adjudicated.
    """
    if not config.get("continue_after_provider_failure", False):
        return False
    if row.get("valid_for_success_rate") or row.get("complete"):
        return False
    return classify_provider_failure(root).get("recoverable_provider_failure", False)


def case_ports(config, slot):
    """Return remote and local service ports for one worker slot."""
    return (
        int(config.get("sim_port_base", 19340)) + slot,
        int(config.get("policy_port_base", 6230)) + slot,
        int(config.get("local_sim_port_base", 29340)) + slot,
        int(config.get("local_policy_port_base", 26230)) + slot,
    )


def parallel_case_workers(config, pending, task_count):
    requested = int(config.get("parallel_case_workers", task_count))
    if requested < 1 or requested > 8:
        raise ValueError("parallel_case_workers must be between 1 and 8")
    return min(requested, len(pending))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", choices=METHODS)
    parser.add_argument("--smoke-decisions", type=int, default=0)
    parser.add_argument("--smoke-slot", type=int, default=5)
    parser.add_argument("--resume-from", type=Path)
    args = parser.parse_args()
    cfg, panel = json.loads(args.config.read_text()), json.loads(args.panel.read_text())
    validate_reasoner_backend(cfg)
    validate_baseline_cadence(cfg, args.smoke)
    validate_panel(panel)
    if args.smoke:
        cfg.update(smoke_decisions=args.smoke_decisions, smoke_slot=args.smoke_slot)
    elif args.smoke_decisions:
        parser.error("a decision budget is only available with --smoke")
    accepted, previous_attempts = (
        resume_outcomes(args.resume_from, panel) if args.resume_from else ([], [])
    )
    if args.resume_from and args.smoke:
        parser.error("resume is for formal campaigns only")
    cluster = Cluster(cfg)
    runtime_identity = verify_policy_runtime(cluster, cfg)
    args.output.mkdir(parents=True, exist_ok=False)
    save_json(args.output / "panel.json", panel)
    save_json(args.output / "config.json", cfg)
    save_json(args.output / "runtime-identity.json", runtime_identity)
    save_json(args.output / "previous-attempts.json", previous_attempts)
    if args.smoke:
        upstream = json.loads(Path(cfg["upstream_panel"]).read_text())
        case = next(
            c for c in upstream["cases"] if c["task"] == "build_tower" and c["layout_id"] == 5
        )
        result = episode(cluster, panel, case, args.smoke, cfg.get("smoke_slot", 5), args.output)
        save_json(args.output / "smoke-result.json", result)
        print(json.dumps(result), flush=True)
        if not result["valid_for_success_rate"]:
            raise SystemExit(2)
        return
    if cfg.get("smoke_decisions", 0):
        raise ValueError("smoke decision budget is forbidden in the formal panel")
    lock, stopped, outcomes = threading.Lock(), threading.Event(), accepted
    completed = {(row["method"], row["case_id"]) for row in accepted}
    save_json(args.output / "outcomes.json", outcomes)
    save_json(args.output / "comparison.json", summarize(panel, outcomes))

    pending = cases_requiring_work(panel, completed)
    if not pending:
        finish_campaign(args.output, panel, outcomes, stopped=False)
        return
    work = queue.Queue()
    for case in pending:
        work.put(case)

    def worker(slot):
        while not stopped.is_set():
            try:
                case = work.get_nowait()
            except queue.Empty:
                return
            for method in panel["methods"]:
                if (method, case["case_id"]) in completed:
                    continue
                if stopped.is_set():
                    return
                row = episode(cluster, panel, case, method, slot, args.output)
                with lock:
                    outcomes.append(row)
                    save_json(args.output / "outcomes.json", outcomes)
                    save_json(args.output / "comparison.json", summarize(panel, outcomes))
                print(json.dumps(dict(event="episode_finished", **row)), flush=True)
                if not row["valid_for_success_rate"] and not may_continue_after_invalid(
                    cfg, args.output, row
                ):
                    stopped.set()
                    return

    tasks = list(dict.fromkeys(c["task"] for c in panel["cases"]))
    worker_count = parallel_case_workers(cfg, pending, len(tasks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(worker, slot) for slot in range(worker_count)]
        for future in futures:
            future.result()
    finish_campaign(args.output, panel, outcomes, stopped=stopped.is_set())


if __name__ == "__main__":
    main()
