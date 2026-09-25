"""Own one campaign process and retain its exit evidence; never retry it."""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def supervise(root, command):
    root.mkdir(parents=True, exist_ok=False)
    started = time.time()
    receipt = {
        "schema": "starharness.supervisor.v1",
        "supervisor_pid": os.getpid(),
        "started_at": started,
        "command": command,
        "finished": False,
    }
    write_json(root / "process.json", receipt)
    process = None
    received_signals = []

    def forward(signum, _frame):
        received_signals.append(signum)
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with (root / "campaign.log").open("x") as log:
            process = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            receipt.update(pid=process.pid)
            try:
                receipt["start_ticks"] = (
                    Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
                )
            except FileNotFoundError:
                pass  # An immediately failing child still has an exit receipt.
            write_json(root / "process.json", receipt)
            while True:
                try:
                    code = process.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    write_json(root / "heartbeat.json", {"observed_alive_at": time.time(),
                                                         "pid": process.pid})
            receipt.update(returncode=code)
            return code
    except BaseException as error:
        receipt.update(supervisor_error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        receipt.update(finished=True, finished_at=time.time(), received_signals=received_signals)
        write_json(root / "exit.json", receipt)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a campaign command is required after --")
    raise SystemExit(supervise(args.state_dir, command))


if __name__ == "__main__":
    main()
