"""Run/stop one remotely owned service using a PID plus process-start identity."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def start_ticks(pid):
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", type=Path)
    args = parser.parse_args()
    if args.stop:
        receipt = json.loads(args.stop.read_text())
        pid = receipt["pid"]
        try:
            if start_ticks(pid) != receipt["start_ticks"] or os.getpgid(pid) != pid:
                raise RuntimeError("service PID was reused; refusing to signal")
            os.killpg(pid, signal.SIGTERM)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if start_ticks(pid) != receipt["start_ticks"]:
                    return
                time.sleep(0.5)
            if start_ticks(pid) == receipt["start_ticks"] and os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGKILL)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        if start_ticks(pid) != receipt["start_ticks"]:
                            return
                    except FileNotFoundError:
                        return
                    time.sleep(0.25)
                raise RuntimeError("service did not exit after SIGKILL")
        except ProcessLookupError:
            pass
        except FileNotFoundError:
            pass
        return
    config = json.load(sys.stdin)
    root = Path(config["output"])
    root.mkdir(parents=True, exist_ok=False)
    (root / "service_config.json").write_text(json.dumps(config, indent=2))
    environment = dict(os.environ, **config.get("environment", {}))
    with (root / "service.log").open("w") as stream:
        process = subprocess.Popen(
            config["command"],
            cwd=config["cwd"],
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        receipt = {"pid": process.pid, "start_ticks": start_ticks(process.pid)}
        (root / "process.json").write_text(json.dumps(receipt))
        print(json.dumps(receipt), flush=True)
        code = process.wait()
    (root / "exit.json").write_text(json.dumps({"returncode": code}))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
