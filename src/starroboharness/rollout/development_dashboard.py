"""Live comparison table for retained off-panel development episodes.

This dashboard deliberately keeps development evidence separate from a formal
campaign.  A running or missing episode is never displayed as a zero-success
terminal result.
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .monitor import Reader


def _process_is_live(root, supervisor, reader):
    process = reader.read(supervisor / "process.json", {}) if supervisor else {}
    exit_receipt = reader.read(supervisor / "exit.json", {}) if supervisor else {}
    if exit_receipt.get("finished"):
        return False
    pid = process.get("pid")
    if not pid:
        return None
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        live = os.fsencode(str(root)) in command
        if live and process.get("start_ticks"):
            ticks = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
            live = ticks == process["start_ticks"]
        return live
    except OSError:
        return False


def _episode(root, supervisor, reader):
    result = reader.read(root / "smoke-result.json", {})
    progress_paths = sorted(root.glob("*/*/controller/progress.json"))
    progress_path = progress_paths[0] if progress_paths else None
    progress = reader.read(progress_path, {}) if progress_path else {}
    if result.get("valid_for_success_rate") is True:
        status = "SUCCESS" if result.get("success") is True else "FAIL"
    else:
        live = _process_is_live(root, supervisor, reader)
        status = "RUNNING" if live else "INTERRUPTED" if live is False else "NOT STARTED"
    metrics = result.get("metrics", progress)
    return {
        "status": status,
        "score": result.get("score"),
        "steps": metrics.get("step_id", 0),
        "decisions": metrics.get("decisions", 0),
        "reasoner_calls": metrics.get("reasoner_calls", 0),
        "policy_calls": metrics.get("policy_calls", 0),
        "correction_steps": metrics.get("correction_steps", 0),
        "wall_seconds": result.get("wall_seconds", metrics.get("wall_seconds")),
        "age": int(time.time() - progress_path.stat().st_mtime) if progress_path else None,
    }


def _format_score(value):
    return "--" if value is None else f"{100 * value:.0f}"


def _format_wall(value):
    return "--" if value is None else f"{value / 60:.1f}m"


def _formal_status(root, planned, reader):
    panel = reader.read(root / "panel.json")
    rows = reader.read(root / "outcomes.json", [])
    if not panel:
        return f"NOT STARTED | 0/{planned} valid terminal episodes"
    valid = sum(row.get("valid_for_success_rate") is True for row in rows)
    complete = valid == planned
    state = "COMPLETE" if complete else "IN PROGRESS"
    return f"{state} | {valid}/{planned} valid terminal episodes"


def render(entries, formal_root, formal_planned, reader):
    reader.warnings = []
    rows = [(label, _episode(root, supervisor, reader)) for label, root, supervisor in entries]
    lines = [
        "StarRoboHarness | LATEST RESULT TABLE | "
        + datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "OFF-PANEL DEVELOPMENT — one retained build_tower/layout5 episode per row",
        "Do not interpret these rows as the five-task formal success rate.",
        "",
        f"{'Method':24} {'Native result':16} {'Score':7} {'Steps':11} "
        f"{'Decisions':10} {'GPT turns':10} {'Policy':8} {'Corrections':12} {'Wall':8}",
    ]
    for label, row in rows:
        result = row["status"]
        if result in {"SUCCESS", "FAIL"}:
            result += " (1 valid)"
        lines.append(
            f"{label:24} {result:16} {_format_score(row['score']):7} "
            f"{str(row['steps']) + '/1050':11} {row['decisions']:<10} "
            f"{row['reasoner_calls']:<10} {row['policy_calls']:<8} "
            f"{row['correction_steps']:<12} {_format_wall(row['wall_seconds']):8}"
        )
    running = [(label, row) for label, row in rows if row["status"] == "RUNNING"]
    for label, row in running:
        age = "unknown" if row["age"] is None else f"{row['age']}s"
        lines.append(f"LIVE: {label} last acknowledged progress {age} ago")
    lines += [
        "",
        f"FORMAL FIVE-TASK CAMPAIGN: {_formal_status(formal_root, formal_planned, reader)}",
        f"Formal output: {formal_root}",
        "Development report: docs/iterations/2026-09-18-v0.1.0-alpha.2.md",
        "Refresh: 5s | detach: Ctrl-b then d | choose windows: Ctrl-b then w",
    ]
    if reader.warnings:
        lines.append(
            f"Reading {len(reader.warnings)} changing/unreadable JSON file(s); "
            "using the last good snapshot."
        )
    return "\n".join(lines)


def _entry(value):
    try:
        label, root, supervisor = value.split("=", 2)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected LABEL=ROOT=SUPERVISOR") from error
    return label, Path(root).resolve(), Path(supervisor).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--entry",
        action="append",
        required=True,
        type=_entry,
        metavar="LABEL=ROOT=SUPERVISOR",
    )
    parser.add_argument("--formal-root", required=True, type=Path)
    parser.add_argument("--formal-planned", type=int, default=75)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("interval must be at least one second")
    reader = Reader()
    while True:
        try:
            screen = render(
                args.entry,
                args.formal_root.resolve(),
                args.formal_planned,
                reader,
            )
        except (OSError, ValueError, KeyError) as error:
            screen = f"Dashboard read error (runners unchanged): {type(error).__name__}: {error}"
        print(
            ("\033[2J\033[H" if sys.stdout.isatty() and not args.once else "") + screen,
            flush=True,
        )
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
