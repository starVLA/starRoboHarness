"""Scan tracked text for common credentials and site-specific identifiers.

This is a publication gate, not proof that history is secret-free.
Only filenames are printed to avoid exposing matched values.
"""

import re
import subprocess
from pathlib import Path

PATTERNS = (
    r"(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{20,}",
    r"sk-[A-Za-z0-9_-]{20,}",
    r"/(?:fsx|apdcephfs[^/]*|data/s3)/",
    r"\b(?:envaws\d+|jiehui-audio-\d+)\b",
    r"[A-Za-z0-9._%+-]+@(?:gmail|qq)\.com",
    r"appgprj_[A-Za-z0-9]+",
)


def main():
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    bad = []
    for name in filter(None, names):
        path = root / name
        if path == Path(__file__).resolve() or not path.is_file():
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            continue
        if any(re.search(pattern, content) for pattern in PATTERNS):
            bad.append(name)
    for name in bad:
        print("Review required:", name)
    if bad:
        raise SystemExit(1)
    print("Tracked-tree content scan passed; review history and binary assets separately.")


if __name__ == "__main__":
    main()
