"""Read-only terminal dashboard; tolerate partially written live JSON files."""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from ..evaluation import summarize

LABELS = {
    "qwenpi_v3": "StarVLA/QwenPI_v3",
    "qwenpi_v3_plus_gpt": "Astra + StarVLA",
    "gpt_direct": "Astra Direct",
}


def process_matches_root(pid, root, start_ticks=None):
    """Verify a campaign PID even when its output path uses a shared-FS alias."""
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        encoded_root = os.fsencode(str(root))
        matches = encoded_root in command
        if not matches and b"--output" in command:
            output_index = command.index(b"--output") + 1
            if output_index < len(command) and command[output_index]:
                output = Path(os.fsdecode(command[output_index])).resolve()
                matches = output == root
        if matches and start_ticks:
            ticks = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
            matches = ticks == start_ticks
        return matches
    except OSError:
        return False


class Reader:
    def __init__(self):
        self.cache = {}
        self.warnings = []

    def read(self, path, default=None):
        path = Path(path)
        try:
            value = json.loads(path.read_text())
            # The native controller and persistent reasoner intentionally share
            # progress.json: the controller records the physical ACK first and
            # the reasoner enriches it with usage/call timing immediately after.
            # Preserve enrichment fields during that short valid-but-sparse
            # intermediate write so the live dashboard never flashes counters
            # back to zero.
            previous = self.cache.get(path)
            if (path.name == "progress.json" and isinstance(previous, dict)
                    and isinstance(value, dict)):
                value = {**previous, **value}
            self.cache[path] = value
            return value
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            self.warnings.append(str(path))
            return self.cache.get(path, default)


def cell(metric, running=0):
    if not metric["valid"]:
        if running:
            return f"RUNNING {running}/{metric['planned']} [0 valid]"
        return f"pending [0/{metric['planned']}]"
    result = (
        f"{metric['successes']}/{metric['valid']}={metric['success_rate']:.0%} "
        f"S:{metric['score']:.0f} [{metric['valid']}/{metric['planned']}]"
    )
    return result + (f" +{running} run" if running else "")


def render_development(root, reader, live, exit_receipt):
    result = reader.read(root / "smoke-result.json", {})
    phase = ("FINISHED" if result else "INTERRUPTED" if live is False else
             "RUNNING" if live else "PID NOT VERIFIED")
    lines = ["starRoboHarness | OFF-PANEL DEVELOPMENT | " + phase,
             "Development evidence only; excluded from the formal 75-episode comparison."]
    for path in sorted(root.glob("*/*/case.json")):
        directory = path.parent
        progress = reader.read(directory / "controller/progress.json", {})
        error = reader.read(directory / "error.json", {})
        identity = reader.read(directory / "reasoner/identity.json", {})
        decisions = progress.get("decisions")
        if decisions is None:
            history = reader.read(directory / "controller/history.json", [])
            decisions = len(history) if history else "not reported"
        stage = ("ERROR: " + error.get("type", "unknown") if error else
                 "INTERRUPTED" if live is False and not result else
                 "NATIVE TERMINAL" if result.get("valid_for_success_rate") else
                 "INCOMPLETE" if result else
                 "CONTROL" if progress.get("step_id", 0) > 0 else
                 "AGENT / FIRST ACTION" if identity else "SERVICE STARTUP / HANDSHAKE")
        policy_calls = progress.get("policy_calls", progress.get("predictions", "not reported"))
        lines += [
            "",
            f"{directory.parent.name} / {directory.name}",
            f"State: {stage} | native steps: {progress.get('step_id', 0)}",
            f"Decisions: {decisions} | policy calls: {policy_calls}",
        ]
        if progress:
            age = int(time.time() - (directory / "controller/progress.json").stat().st_mtime)
            lines.append(f"Last recorded progress: {age}s ago")
        usage = reader.read(directory / "reasoner/usage.json", {})
        lines.append(f"Reported model token usage: {json.dumps(usage)}")
    if result:
        lines.append(f"Native valid: {result.get('valid_for_success_rate')} | "
                     f"success: {result.get('success')} | score: {result.get('score')}")
    if exit_receipt:
        lines.append(f"Runner exit code: {exit_receipt.get('returncode', 'unknown')}")
    lines += ["", f"Root: {root}", "Refresh: 5s | detach: Ctrl-b then d"]
    return "\n".join(lines)


def render(root, reader, pid=None, supervisor=None):
    reader.warnings = []
    panel = reader.read(root / "panel.json")
    rows = reader.read(root / "outcomes.json", [])
    if not panel:
        return "Waiting for panel.json: " + str(root)
    report = summarize(panel, rows)
    method_order = tuple(panel["methods"])
    cfg = reader.read(root / "config.json", {})
    status = reader.read(root / "campaign-status.json", {})
    live = None
    process = reader.read(supervisor / "process.json", {}) if supervisor else {}
    exit_receipt = reader.read(supervisor / "exit.json", {}) if supervisor else {}
    if supervisor:
        pid = process.get("pid")
    if pid:
        live = process_matches_root(pid, root, process.get("start_ticks"))
    if exit_receipt.get("finished"):
        live = False
    if "smoke_slot" in cfg:
        return render_development(root, reader, live, exit_receipt)
    state = (
        "COMPLETE"
        if report["complete"]
        else "STOPPED / INCOMPLETE"
        if status.get("finished") or live is False
        else "RUNNING"
        if live
        else "PID not tracked"
    )
    completed = {(row["method"], row["case_id"]) for row in rows}
    task_by_case = {case["case_id"]: case["task"] for case in panel["cases"]}
    running = {}
    if state == "RUNNING":
        for progress_path in root.glob("*/*/controller/progress.json"):
            directory = progress_path.parent.parent
            method, case_id = directory.parent.name, directory.name
            if (method, case_id) in completed or (directory / "error.json").exists():
                continue
            task = task_by_case.get(case_id)
            if task:
                running[(task, method)] = running.get((task, method), 0) + 1
    valid = sum(row.get("valid_for_success_rate") is True for row in rows)
    lines = [
        "starRoboHarness | LIVE EVALUATION | "
        + datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        f"{state} | valid episodes {valid}/{len(panel['cases']) * len(method_order)} | "
        f"paired cases {len(report['paired_case_ids'])}/{len(panel['cases'])}",
        f"Sim: {cfg.get('sim_pod', '?')} | Policy: {cfg.get('policy_pod', '?')} | "
        "GPU contention: shared",
        "Terminal results are scored above; RUNNING is live, pending is not zero success.",
        "",
        f"{'Task':30}" + "".join(f"{LABELS[name]:27}" for name in method_order),
    ]
    for task, task_methods in report["tasks"].items():
        lines.append(
            f"{task:30}"
            + "".join(
                f"{cell(task_methods[m], running.get((task, m), 0)):27}"
                for m in method_order
            )
        )
    running_by_method = {
        selected: sum(value for (_task, method), value in running.items() if method == selected)
        for selected in method_order
    }
    lines.append(
        f"{'OVERALL (partial)':30}"
        + "".join(
            f"{cell(report['methods'][method], running_by_method[method]):27}"
            for method in method_order
        )
    )
    lines += [
        "",
        "ACTIVE RUNS / RECENT ERRORS",
        f"{'Method / case':73} {'Steps':11} {'GPT calls':10} {'Last ACK':10} State",
    ]
    limits = {}
    total_calls = total_tokens = 0
    for case_path in sorted(root.glob("*/*/case.json")):
        directory = case_path.parent
        method, case_id = directory.parent.name, directory.name
        progress = reader.read(directory / "controller/progress.json", {})
        total_calls += progress.get("reasoner_calls", 0)
        total_tokens += progress.get("usage", {}).get("input_tokens", 0) + progress.get(
            "usage", {}
        ).get("output_tokens", 0)
        error = reader.read(directory / "error.json")
        if (method, case_id) in completed and not error:
            continue
        requests = sorted((directory / "controller").glob("request_*.json"))
        if requests:
            limits[case_id] = reader.read(requests[-1], {}).get("max_episode_steps", "?")
        step = progress.get("step_id", 0)
        age = (
            f"{int(time.time() - (directory / 'controller/progress.json').stat().st_mtime)}s"
            if progress
            else "--"
        )
        phase = (
            "ERROR: " + error.get("type", "unknown")
            if error
            else "INTERRUPTED / NO TERMINAL RESULT"
            if state == "STOPPED / INCOMPLETE"
            else "UNVERIFIED / PID NOT TRACKED"
            if live is None
            else "CONTROL"
            if progress
            else "STARTING / FIRST DECISION"
        )
        lines.append(
            f"{method + ' / ' + case_id:73} "
            f"{str(step) + '/' + str(limits.get(case_id, '?')):11} "
            f"{progress.get('reasoner_calls', 0):<10} {age:10} {phase}"
        )
    lines += [
        "",
        f"Acknowledged GPT calls: {total_calls} | input+output tokens: {total_tokens:,}",
        "Counters update after control ACK; initial in-flight calls are not included.",
        f"Root: {root}",
        "Refresh: 5s by default | tmux detach: Ctrl-b then d | logs: tmux window 1",
    ]
    if reader.warnings:
        lines.append(
            f"Reading {len(reader.warnings)} changing/unreadable JSON file(s); "
            "using last good snapshot."
        )
    if exit_receipt:
        lines.append(f"Runner exit code: {exit_receipt.get('returncode', 'not recorded')}; "
                     f"signals: {exit_receipt.get('received_signals', [])}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--supervisor", type=Path, help="supervisor state directory")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("interval must be at least one second")
    root, reader = args.campaign.resolve(), Reader()
    while True:
        try:
            screen = render(root, reader, args.pid, args.supervisor)
        except (OSError, ValueError, KeyError) as error:
            screen = f"Dashboard read error (runner unchanged): {type(error).__name__}: {error}"
        print(
            ("\033[2J\033[H" if sys.stdout.isatty() and not args.once else "") + screen, flush=True
        )
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
