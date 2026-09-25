"""Stage an immutable source/case snapshot to CVM and both evaluation pods."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    source = Path(__file__).resolve().parents[1]
    snapshot = Path(config["remote_source"])
    snapshot.mkdir(parents=True, exist_ok=False)
    for name in ("src", "scripts", "configs", "skills"):
        shutil.copytree(
            source / name, snapshot / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
    for name in ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(source / name, snapshot / name)
    from hybrid_rollout.robodojo.evaluation import case_identity, read_panel

    upstream = read_panel(config["upstream_panel"])
    (snapshot / "cases").mkdir()
    for case in upstream["cases"]:
        (snapshot / "cases" / (case["case_id"] + ".json")).write_text(
            json.dumps({"case": case, "identity": case_identity(upstream, case)}, indent=2)
        )
    digests = {
        str(path.relative_to(snapshot)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(snapshot.rglob("*"))
        if path.is_file()
    }
    (snapshot / "source_manifest.json").write_text(json.dumps(digests, indent=2))
    archive = snapshot.with_suffix(".tar")
    subprocess.run(["tar", "-cf", str(archive), "-C", str(snapshot), "."], check=True)
    for pod in dict.fromkeys((config["sim_pod"], config["policy_pod"])):
        import shlex

        # Multiple pods can share the same FSx mount; validate an existing snapshot.
        manifest_sha = hashlib.sha256((snapshot / "source_manifest.json").read_bytes()).hexdigest()
        verify = (
            "import hashlib,json,sys; from pathlib import Path; "
            "sys.stdin.buffer.read(); "
            f"root=Path({str(snapshot)!r}); p=root/'source_manifest.json'; "
            f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={manifest_sha!r}; "
            "assert all(hashlib.sha256((root/k).read_bytes()).hexdigest()==v "
            "for k,v in json.loads(p.read_text()).items())"
        )
        command = (
            f"mkdir -p {shlex.quote(str(snapshot.parent))} && "
            f"if test -e {shlex.quote(str(snapshot))}; then "
            f"{shlex.quote(config['remote_python'])} -c {shlex.quote(verify)}; else "
            f"mkdir {shlex.quote(str(snapshot))} && tar -xf - -C {shlex.quote(str(snapshot))}; "
            f"fi && mkdir -p {shlex.quote(config['xdg_runtime'])} "
            f"&& chmod 700 {shlex.quote(config['xdg_runtime'])}"
        )
        with archive.open("rb") as stream:
            subprocess.run(
                [
                    "kubectl",
                    "--context",
                    config["context"],
                    "-n",
                    config["namespace"],
                    "exec",
                    "-i",
                    pod,
                    "-c",
                    "main",
                    "--",
                    "bash",
                    "-lc",
                    command,
                ],
                stdin=stream,
                check=True,
            )
    print(
        json.dumps(
            {
                "snapshot": str(snapshot),
                "files": len(digests),
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
