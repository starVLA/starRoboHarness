"""Validate and launch one immutable starRoboHarness campaign in detached tmux."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

from starharness.evaluation import panel_digest, validate_panel
from starharness.rollout.campaign import validate_baseline_cadence, validate_reasoner_backend


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_launch(config_path, panel_path, output, supervisor):
    config_path = Path(config_path).resolve(strict=True)
    panel_path = Path(panel_path).resolve(strict=True)
    output, supervisor = Path(output).resolve(), Path(supervisor).resolve()
    config = json.loads(config_path.read_text())
    panel = json.loads(panel_path.read_text())
    validate_reasoner_backend(config)
    validate_baseline_cadence(config, None)
    validate_panel(panel)
    upstream = json.loads(Path(config["upstream_panel"]).read_text())
    if panel.get("upstream_panel_sha256") != upstream.get("panel_sha256"):
        raise ValueError("panel does not belong to the configured frozen upstream manifest")
    if output != Path(config["remote_output"]).resolve():
        raise ValueError("local output must equal config.remote_output on the mirrored FSx paths")
    if output.exists() or supervisor.exists():
        raise FileExistsError("output and supervisor paths must both be fresh")
    # A venv interpreter is commonly a symlink to the system binary. Resolving
    # that symlink discards pyvenv.cfg and silently changes site-packages.
    python = Path(config["controller_python"]).absolute()
    if not python.is_file():
        raise FileNotFoundError(python)
    codex = Path(config["codex"]).resolve(strict=True)
    if config.get("codex_sha256") and file_sha256(codex) != config["codex_sha256"]:
        raise ValueError("Codex executable digest differs from the frozen config")
    pythonpath = [Path(path).resolve(strict=True) for path in config["controller_pythonpath"]]
    source_manifest = Path(config["remote_source"]) / "source_manifest.json"
    if not source_manifest.is_file():
        raise FileNotFoundError("staged source manifest is missing")
    for relative, digest in json.loads(source_manifest.read_text()).items():
        if file_sha256(source_manifest.parent / relative) != digest:
            raise ValueError(f"staged source digest mismatch: {relative}")
    return {
        "config": config,
        "panel": panel,
        "config_path": config_path,
        "panel_path": panel_path,
        "output": output,
        "supervisor": supervisor,
        "python": python,
        "codex": codex,
        "pythonpath": pythonpath,
        "panel_sha256": panel_digest(panel),
        "config_sha256": file_sha256(config_path),
    }


def runner_command(launch):
    campaign = [
        str(launch["python"]),
        "-m",
        "starharness.rollout.campaign",
        "--config",
        str(launch["config_path"]),
        "--panel",
        str(launch["panel_path"]),
        "--output",
        str(launch["output"]),
    ]
    if launch.get("resume_from"):
        campaign.extend(["--resume-from", str(launch["resume_from"])])
    return [
        "env",
        "PYTHONPATH=" + os.pathsep.join(str(path) for path in launch["pythonpath"]),
        "PYTHONUNBUFFERED=1",
        str(launch["python"]),
        "-m",
        "starharness.rollout.supervisor",
        "--state-dir",
        str(launch["supervisor"]),
        "--",
        *campaign,
    ]


def probe_codex(launch):
    provider = launch["config"]["codex_provider"]
    if provider == "openai":
        status = subprocess.run(
            [str(launch["codex"]), "login", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if status.returncode:
            raise RuntimeError("native Codex account login is unavailable")
    command = [
        str(launch["codex"]), "exec", "--ephemeral", "--skip-git-repo-check", "--json",
        "-m", "gpt-6-astra", "-c", f"model_provider={json.dumps(provider)}",
        "-c", 'model_reasoning_effort="xhigh"', "-c", "features.apps=false",
        "-c", "features.plugins=false", "-c", "features.multi_agent=false",
        "-c", 'web_search="disabled"',
        "Reply with exactly STARHARNESS_PROVIDER_READY",
    ]
    attempts = int(launch["config"].get("codex_probe_attempts", 3))
    if attempts < 1 or attempts > 5:
        raise ValueError("codex_probe_attempts must be between 1 and 5")
    probe = None
    for attempt in range(1, attempts + 1):
        probe = subprocess.run(command, capture_output=True, text=True, timeout=240)
        if probe.returncode == 0:
            break
        if attempt < attempts:
            import time

            time.sleep(min(2 ** (attempt - 1), 4))
    if probe is None or probe.returncode:
        raise RuntimeError(f"Codex provider preflight failed for {provider}")
    messages, usage = [], None
    for line in probe.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                messages.append(item.get("text"))
        elif event.get("type") == "turn.completed":
            usage = event.get("usage")
    if messages[-1:] != ["STARHARNESS_PROVIDER_READY"] or usage is None:
        raise RuntimeError(f"Codex provider preflight returned unexpected output for {provider}")
    return {"model": "gpt-6-astra", "effort": "xhigh", "provider": provider,
            "response": messages[-1], "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--supervisor", type=Path, required=True)
    parser.add_argument("--tmux-session", required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--resume-from", type=Path)
    args = parser.parse_args()
    launch = validate_launch(args.config, args.panel, args.output, args.supervisor)
    if args.resume_from:
        from starharness.rollout.campaign import resume_outcomes

        launch["resume_from"] = args.resume_from.resolve(strict=True)
        resume_outcomes(launch["resume_from"], launch["panel"])
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in launch["pythonpath"])
    probe = subprocess.run(
        [str(launch["python"]), "-m", "starharness.rollout.runtime_preflight"],
        env=environment, capture_output=True, text=True, timeout=90,
    )
    if probe.returncode:
        raise RuntimeError("Controller dependency preflight failed:\n" + probe.stderr[-6000:])
    controller_identity = json.loads(probe.stdout)
    codex_identity = probe_codex(launch)
    summary = {
        "panel_sha256": launch["panel_sha256"],
        "config_sha256": launch["config_sha256"],
        "tasks": list(dict.fromkeys(case["task"] for case in launch["panel"]["cases"])),
        "cases": len(launch["panel"]["cases"]),
        "methods": launch["panel"]["methods"],
        "episodes": len(launch["panel"]["cases"]) * len(launch["panel"]["methods"]),
        "provider": launch["config"]["codex_provider"],
        "output": str(launch["output"]),
        "supervisor": str(launch["supervisor"]),
        "controller_identity": controller_identity,
        "codex_identity": codex_identity,
    }
    if args.check_only:
        print(json.dumps(dict(status="ready", **summary), indent=2))
        return
    # tmux target names use prefix matching by default.  Exact matching is
    # important here: a launcher session such as ``unitypolicy-v8-launch``
    # must not make the requested ``unitypolicy-v8`` session look occupied.
    tmux_target = "=" + args.tmux_session
    existing = subprocess.run(
        ["tmux", "has-session", "-t", tmux_target], capture_output=True
    )
    if existing.returncode == 0:
        raise FileExistsError(f"tmux session already exists: {args.tmux_session}")
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            args.tmux_session,
            "-n",
            "runner",
            shlex.join(runner_command(launch)),
        ],
        check=True,
    )
    monitor = [
        "env",
        "PYTHONPATH=" + os.pathsep.join(str(path) for path in launch["pythonpath"]),
        str(launch["python"]),
        "-m",
        "starharness.rollout.monitor",
        str(launch["output"]),
        "--supervisor",
        str(launch["supervisor"]),
    ]
    subprocess.run(
        [
            "tmux",
            "new-window",
            "-t",
            tmux_target,
            "-n",
            "dashboard",
            shlex.join(monitor),
        ],
        check=True,
    )
    subprocess.run(
        ["tmux", "select-window", "-t", f"{tmux_target}:dashboard"], check=True
    )
    print(json.dumps(dict(status="launched", tmux=args.tmux_session, **summary), indent=2))
    print(f"tmux attach -t {shlex.quote(tmux_target)}")


if __name__ == "__main__":
    main()
