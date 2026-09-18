"""Run StarRoboHarness sequentially on one host with separate policy and simulator GPUs.

The controller runs in the current Python environment.  StarVLA and RoboDojo are
started as isolated process groups with their own Python executables and environments.
This entrypoint deliberately does not retry an episode after robot control begins.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

from ..adapters.qwenpi_v3 import QwenPIv3Adapter
from ..evaluation import METHODS, panel_digest, summarize, validate_panel
from ..reasoners import CodexCLIReasoner
from .controller import Controller, StarVLAConnection, method_profile, save_json

METHOD_ORDER = ("qwenpi_v3", "qwenpi_v3_plus_gpt", "gpt_direct")
POLICY_READY = "server listening"
SIM_READY = '"event": "ready"'
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VENDORED_SOURCE = REPOSITORY_ROOT / "src"
RUNTIME_PATH_KEYS = (
    "starvla_source",
    "starvla_base_vlm",
    "checkpoint",
    "robodojo_source",
    "upstream_panel",
    "policy_python",
    "sim_python",
    "codex",
    "graphics_runtime",
    "xdg_runtime",
)


def resolve_runtime_config(config: dict, root: Path = REPOSITORY_ROOT) -> dict:
    """Resolve repository-relative runtime paths without storing machine paths."""
    root = Path(root)
    resolved = dict(config)
    for key in RUNTIME_PATH_KEYS:
        value = resolved.get(key)
        if value and not Path(value).expanduser().is_absolute():
            resolved[key] = str((root / value).resolve())
    return resolved


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    return resolved


def require_directory(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"{label} is not a directory: {resolved}")
    return resolved


def check_port_available(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise RuntimeError(f"local TCP port is unavailable: {port}") from error


def prepend_pythonpath(environment: dict[str, str], paths: list[str]) -> None:
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = ":".join(paths + ([existing] if existing else []))


def build_policy_process(config: dict, output: Path) -> tuple[list[str], dict[str, str], Path]:
    config = resolve_runtime_config(config)
    source = require_directory(config["starvla_source"], "starvla_source")
    python = require_file(config["policy_python"], "policy_python")
    checkpoint = require_file(config["checkpoint"], "checkpoint")
    base_vlm = require_directory(config["starvla_base_vlm"], "starvla_base_vlm")
    server = require_file(source / "deployment/model_server/server_policy.py", "StarVLA server")
    environment = dict(os.environ)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(config.get("policy_gpu", 0)),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_ALBUMENTATIONS_UPDATE": "1",
            "PYTHONUNBUFFERED": "1",
            "STARVLA_CKPT_PATH": str(checkpoint),
            "STARVLA_BASE_VLM": str(base_vlm),
            "STARVLA_INCLUDE_STATE": "True",
            "STARVLA_UNNORM_KEY": "arx_x5",
            "STARVLA_EXECUTE_HORIZON": "16",
            "STARVLA_IMAGE_SIZE": "[224,224]",
            "STARVLA_REQUIRED_PI_V3_FORWARD": "canonical_interleaved",
        }
    )
    prepend_pythonpath(environment, [str(source)])
    command = [
        str(python),
        str(server),
        "--ckpt_path",
        str(checkpoint),
        "--port",
        str(config.get("policy_port", 6230)),
        "--use_bf16",
        "--idle_timeout",
        "-1",
    ]
    return command, environment, source


def build_sim_process(
    config: dict, case: dict, case_file: Path, output: Path
) -> tuple[list[str], dict[str, str], Path]:
    config = resolve_runtime_config(config)
    upstream = require_directory(VENDORED_SOURCE, "vendored_source")
    robodojo = require_directory(config["robodojo_source"], "robodojo_source")
    python = require_file(config["sim_python"], "sim_python")
    panel = require_file(config["upstream_panel"], "upstream_panel")
    case_file = case_file.expanduser().resolve()
    output = output.expanduser().resolve()
    xdg_runtime = Path(config.get("xdg_runtime", output / "xdg-runtime")).expanduser().resolve()
    xdg_runtime.mkdir(parents=True, exist_ok=True)
    xdg_runtime.chmod(0o700)
    environment = dict(os.environ)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(config.get("sim_gpu", 1)),
            "PYTHONUNBUFFERED": "1",
            "OMNI_KIT_ACCEPT_EULA": "Y",
            "XDG_RUNTIME_DIR": str(xdg_runtime),
            "ROLLOUT_EVAL_MANIFEST_SHA256": json.loads(panel.read_text())["panel_sha256"],
        }
    )
    prepend_pythonpath(
        environment,
        [
            str(upstream),
            str(robodojo),
            str(robodojo / "XPolicyLab"),
            str(robodojo / "third_party/curobo"),
        ],
    )
    if config.get("graphics_runtime"):
        runtime = require_directory(config["graphics_runtime"], "graphics_runtime")
        library_path = ":".join(
            value for value in (str(runtime), environment.get("LD_LIBRARY_PATH")) if value
        )
        environment.update(
            {
                "LD_LIBRARY_PATH": library_path,
                "VK_ICD_FILENAMES": str(runtime / "nvidia_icd.json"),
                "__EGL_VENDOR_LIBRARY_FILENAMES": str(runtime / "10_nvidia.json"),
            }
        )
    command = [
        str(python),
        "-m",
        "hybrid_rollout.robodojo.robodojo_server.server",
        "--task",
        case["runtime_task"],
        "--eval-seed",
        str(case["eval_seed"]),
        "--output",
        str(output / "sim"),
        "--port",
        str(config.get("sim_port", 19340)),
        "--eval-manifest",
        str(panel),
        "--case-file",
        str(case_file),
    ]
    workdir = output / "sim-service"
    workdir.mkdir(parents=True, exist_ok=False)
    return command, environment, workdir


def start_process(command: list[str], environment: dict[str, str], cwd: Path, log_path: Path):
    stream = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except BaseException:
        stream.close()
        raise
    return process, stream


def stop_process(process: subprocess.Popen, timeout: float = 30) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=timeout)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def wait_for_services(
    services: list[tuple[str, subprocess.Popen, Path]], timeout_seconds: int
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        ready = True
        for marker, process, log_path in services:
            if process.poll() is not None:
                raise RuntimeError(
                    f"service exited before readiness ({process.returncode}): {log_path}"
                )
            text = log_path.read_text(errors="replace") if log_path.exists() else ""
            ready = ready and marker in text
        if ready:
            return
        time.sleep(2)
    raise TimeoutError(f"services were not ready in {timeout_seconds} seconds")


def verify_policy_runtime(config: dict) -> dict:
    config = resolve_runtime_config(config)
    required = (
        "checkpoint",
        "checkpoint_sha256",
        "starvla_source",
        "starvla_normalization_patch_sha256",
        "starvla_norm_processor_sha256",
        "starvla_policy_wrapper_sha256",
    )
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError("runtime identity is missing: " + ", ".join(missing))
    checkpoint = require_file(config["checkpoint"], "checkpoint")
    source = require_directory(config["starvla_source"], "starvla_source")
    checkpoint_sha = sha256_file(checkpoint)
    norm_processor = require_file(
        source / "deployment/model_server/policy_norm_processor.py",
        "StarVLA normalization processor",
    )
    policy_wrapper = require_file(
        source / "deployment/model_server/policy_wrapper.py", "StarVLA policy wrapper"
    )
    norm_processor_sha = sha256_file(norm_processor)
    policy_wrapper_sha = sha256_file(policy_wrapper)
    if norm_processor_sha != config["starvla_norm_processor_sha256"]:
        raise ValueError("StarVLA normalization processor differs from runtime config")
    if policy_wrapper_sha != config["starvla_policy_wrapper_sha256"]:
        raise ValueError("StarVLA policy wrapper differs from runtime config")
    repository = Path(
        subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    relative_source = source.relative_to(repository)
    diff = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "diff",
            "--",
            str(relative_source / "deployment/model_server/policy_norm_processor.py"),
            str(relative_source / "deployment/model_server/policy_wrapper.py"),
        ],
        check=True,
        capture_output=True,
    ).stdout
    patch_sha = hashlib.sha256(diff).hexdigest()
    if checkpoint_sha != config["checkpoint_sha256"]:
        raise ValueError("checkpoint SHA-256 differs from the frozen runtime config")
    if patch_sha != config["starvla_normalization_patch_sha256"]:
        raise ValueError("StarVLA normalization patch differs from the frozen runtime config")
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "schema": "starroboharness.runtime_identity.v1",
        "host": socket.gethostname(),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": checkpoint_sha,
        "starvla_source": str(source),
        "starvla_commit": commit,
        "starvla_normalization_patch_sha256": patch_sha,
        "starvla_norm_processor_sha256": norm_processor_sha,
        "starvla_policy_wrapper_sha256": policy_wrapper_sha,
        "verified_before_reset": True,
    }


def add_controller_import_paths(config: dict) -> None:
    config = resolve_runtime_config(config)
    for path in (VENDORED_SOURCE, config["starvla_source"]):
        resolved = str(require_directory(path, path))
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def preflight(config: dict) -> dict:
    """Validate a local runtime without importing Isaac Sim or loading model weights."""
    config = resolve_runtime_config(config)
    policy_port = int(config.get("policy_port", 6230))
    sim_port = int(config.get("sim_port", 19340))
    if policy_port == sim_port:
        raise ValueError("policy_port and sim_port must differ")
    check_port_available(policy_port)
    check_port_available(sim_port)
    policy_command, policy_environment, _ = build_policy_process(config, Path("."))
    upstream = json.loads(require_file(config["upstream_panel"], "upstream_panel").read_text())
    smoke = next(
        (
            case
            for case in upstream["cases"]
            if case["task"] == "build_tower" and case["layout_id"] == 5
        ),
        None,
    )
    if smoke is None:
        raise ValueError("upstream panel has no build_tower layout-5 smoke case")
    starvla = require_directory(config["starvla_source"], "starvla_source")
    source_checks = {
        "state_normalization_entrypoint": "def apply_state" in (
            starvla / "deployment/model_server/policy_norm_processor.py"
        ).read_text(),
        "canonical_interleaved_forward": "use_canonical_forward" in (
            starvla
            / "starVLA/model/modules/action_model/flow_matching_head/cross_attention_dit.py"
        ).read_text(),
    }
    if not all(source_checks.values()):
        raise ValueError("StarVLA source does not expose the required QwenPI_v3 contract")
    sim_python = require_file(config["sim_python"], "sim_python")
    version_probe = subprocess.run(
        [
            str(sim_python),
            "-c",
            "import importlib.metadata as m; print(m.version('isaacsim'))",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    if not version_probe.startswith("5.1."):
        raise ValueError(f"RoboDojo requires Isaac Sim 5.1, got {version_probe}")
    codex = require_file(config["codex"], "codex")
    login = subprocess.run(
        [str(codex), "login", "status"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if login.returncode:
        raise ValueError("Codex is not logged in")
    return {
        "schema": "starroboharness.local_preflight.v1",
        "host": socket.gethostname(),
        "policy_gpu": str(config.get("policy_gpu", 0)),
        "sim_gpu": str(config.get("sim_gpu", 1)),
        "policy_port": policy_port,
        "sim_port": sim_port,
        "isaacsim_version": version_probe,
        "codex_status": (login.stdout + login.stderr).strip(),
        "source_checks": source_checks,
        "smoke_case_id": smoke["case_id"],
        "policy_command": policy_command,
        "policy_pythonpath": policy_environment["PYTHONPATH"],
    }


def episode(config: dict, panel: dict, case: dict, method: str, root: Path) -> dict:
    config = resolve_runtime_config(config)
    root = root.expanduser().resolve()
    case_root = root / method / case["case_id"]
    case_root.mkdir(parents=True, exist_ok=False)
    from hybrid_rollout.robodojo.evaluation import case_identity
    from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient

    upstream = json.loads(Path(config["upstream_panel"]).read_text())
    selected = {"identity": case_identity(upstream, case), "case": case}
    case_file = case_root / "case.json"
    save_json(case_file, selected)
    learned = method != "gpt_direct"
    policy_port = int(config.get("policy_port", 6230))
    sim_port = int(config.get("sim_port", 19340))
    check_port_available(sim_port)
    if learned:
        check_port_available(policy_port)
    processes: list[tuple[subprocess.Popen, object]] = []
    connection = sim = None
    started = time.monotonic()
    native_path = case_root / "sim/evaluation_outcome.json"
    outcome = {
        "method": method,
        "implementation_variant": method_profile(method)["implementation_variant"],
        "case_id": case["case_id"],
        "panel_sha256": panel_digest(panel),
        "complete": False,
        "valid_for_success_rate": False,
        "termination": "infrastructure_error",
        "artifact": str(native_path),
    }
    save_json(case_root / "outcome.json", outcome)
    try:
        readiness = []
        if learned:
            command, environment, cwd = build_policy_process(config, case_root / "policy")
            process, stream = start_process(
                command, environment, cwd, case_root / "policy-service.log"
            )
            processes.append((process, stream))
            readiness.append((POLICY_READY, process, case_root / "policy-service.log"))
        command, environment, cwd = build_sim_process(config, case, case_file, case_root)
        process, stream = start_process(command, environment, cwd, case_root / "sim-service.log")
        processes.append((process, stream))
        readiness.append((SIM_READY, process, case_root / "sim-service.log"))
        wait_for_services(readiness, int(config.get("startup_timeout_seconds", 900)))
        adapter = None
        if learned:
            connection = StarVLAConnection(policy_port, case_root / "raw-policy")
            save_json(case_root / "policy-metadata.json", connection.metadata)
            adapter = QwenPIv3Adapter(
                connection.infer,
                server_metadata=connection.metadata,
                native_gripper_clip=True,
            )
        reasoner = (
            None
            if method == "qwenpi_v3"
            else CodexCLIReasoner(
                case_root / "reasoner",
                executable=config["codex"],
                timeout_seconds=int(config.get("reasoner_timeout_seconds", 300)),
            )
        )
        sim = RPCClient("127.0.0.1", sim_port, timeout=600)
        controller = Controller(
            sim=sim,
            method=method,
            case=case,
            output=case_root / "controller",
            policy=adapter,
            reasoner=reasoner,
            smoke_decisions=int(config.get("smoke_decisions", 0)),
        )
        result = controller.run()
        native = json.loads(native_path.read_text())
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
            {"type": type(error).__name__, "traceback": traceback.format_exc()},
        )
        outcome["error_type"] = type(error).__name__
    finally:
        if connection:
            connection.close()
        if sim:
            sim.close()
        if native_path.exists() and not (case_root / "native-outcome.json").exists():
            try:
                save_json(case_root / "native-outcome.json", json.loads(native_path.read_text()))
            except (OSError, ValueError):
                pass
        for process, _stream in reversed(processes):
            stop_process(process)
        for _process, stream in processes:
            stream.close()
        outcome["wall_seconds"] = time.monotonic() - started
        save_json(case_root / "outcome.json", outcome)
    return outcome


def select_methods(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return METHOD_ORDER
    return tuple(method for method in METHOD_ORDER if method in values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", action="append", choices=METHODS)
    parser.add_argument("--smoke", choices=METHODS)
    parser.add_argument("--smoke-decisions", type=int, default=0)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.smoke and args.method:
        parser.error("--smoke and --method cannot be combined")
    if args.preflight and (args.smoke or args.method or args.smoke_decisions):
        parser.error("--preflight cannot be combined with rollout selection arguments")
    if args.smoke_decisions < 0:
        parser.error("--smoke-decisions must be non-negative")
    if args.smoke_decisions and not args.smoke:
        parser.error("a decision budget is only available with --smoke")
    config = resolve_runtime_config(json.loads(args.config.read_text()))
    panel = json.loads(args.panel.read_text())
    validate_panel(panel)
    if args.smoke:
        config["smoke_decisions"] = args.smoke_decisions
    add_controller_import_paths(config)
    runtime_identity = verify_policy_runtime(config)
    preflight_result = preflight(config) if args.preflight else None
    args.output.mkdir(parents=True, exist_ok=False)
    save_json(args.output / "config.json", config)
    save_json(args.output / "panel.json", panel)
    save_json(args.output / "runtime-identity.json", runtime_identity)
    if args.preflight:
        save_json(args.output / "preflight.json", preflight_result)
        print(json.dumps(preflight_result), flush=True)
        return
    if args.smoke:
        upstream = json.loads(Path(config["upstream_panel"]).read_text())
        case = next(
            row
            for row in upstream["cases"]
            if row["task"] == "build_tower" and row["layout_id"] == 5
        )
        result = episode(config, panel, case, args.smoke, args.output)
        save_json(args.output / "smoke-result.json", result)
        print(json.dumps(result), flush=True)
        return
    methods = select_methods(args.method)
    outcomes = []
    save_json(args.output / "outcomes.json", outcomes)
    save_json(args.output / "comparison.json", summarize(panel, outcomes))
    stopped = False
    for case in panel["cases"]:
        for method in methods:
            row = episode(config, panel, case, method, args.output)
            outcomes.append(row)
            save_json(args.output / "outcomes.json", outcomes)
            save_json(args.output / "comparison.json", summarize(panel, outcomes))
            print(json.dumps(dict(event="episode_finished", **row)), flush=True)
            if not row["valid_for_success_rate"]:
                stopped = True
                break
        if stopped:
            break
    expected = len(panel["cases"]) * len(methods)
    save_json(
        args.output / "campaign-status.json",
        {
            "finished": True,
            "complete": len(outcomes) == expected and not stopped,
            "episodes": len(outcomes),
            "expected_episodes": expected,
            "methods": list(methods),
        },
    )


if __name__ == "__main__":
    main()
