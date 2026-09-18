"""Freeze tracked dependency worktree files without touching their source repo.

This intentionally excludes untracked/ignored files. Audit the reported list
before using a snapshot: environment assets and credentials are not vendored.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="1"))


def freeze(source, destination, *, recursive=False, external_links=()):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(destination)
    commit = git(source, "rev-parse", "HEAD").decode().strip()
    patch = git(source, "diff", "--binary", "HEAD", "--")
    omitted = git(source, "ls-files", "--others", "--exclude-standard", "-z")
    # No shared object store or working-tree hardlinks: later source edits cannot
    # alter this copy. Git metadata is retained for existing runtime identity checks.
    subprocess.run(["git", "clone", "--local", "--no-hardlinks", "--no-checkout",
                    str(source), str(destination)], check=True, capture_output=True)
    git(destination, "checkout", "--detach", commit)
    if patch:
        subprocess.run(["git", "-C", str(destination), "apply", "--index", "--binary", "-"],
                       input=patch, check=True, capture_output=True)
    if git(source, "rev-parse", "HEAD").decode().strip() != commit or git(
            source, "diff", "--binary", "HEAD", "--") != patch:
        raise RuntimeError("dependency changed during snapshot; incomplete copy retained")
    submodules = {}
    for record in git(destination, "ls-files", "--stage", "-z").split(b"\0"):
        if not record or not record.startswith(b"160000 "):
            continue
        relative = record.split(b"\t", 1)[1].decode()
        if not recursive:
            raise ValueError("dependency submodule needs separate freeze: " + relative)
        module = destination / relative
        if module.exists():
            module.rmdir()  # Only Git's empty checkout placeholder, never recursive.
        nested = freeze(source / relative, module, recursive=True, external_links=[
            p[len(relative) + 1:] for p in external_links if p.startswith(relative + "/")
        ])
        submodules[relative] = {
            "commit": nested["commit"],
            "manifest_sha256": hashlib.sha256(
                (module / "unitypolicy-dependency.json").read_bytes()).hexdigest(),
        }
    files, symlinks, external_assets = {}, {}, {}
    for raw in git(destination, "ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        relative = raw.decode()
        if relative in submodules:
            continue
        path = destination / relative
        if path.is_symlink():
            if not path.resolve().is_relative_to(destination):
                if relative not in external_links:
                    raise ValueError("external dependency symlink needs asset audit: " + relative)
                external_assets[relative] = os.readlink(path)
            symlinks[relative] = os.readlink(path)
            continue
        if path.exists():
            if not path.is_file():
                raise ValueError("dependency submodule needs separate freeze: " + relative)
            original = source / relative
            if original.is_symlink() or not original.is_file():
                raise ValueError("source file changed type during freeze: " + relative)
            # Checkout may contain LFS pointers. Preserve the bytes already used
            # by this installation, not a fresh download or a pointer substitution.
            shutil.copy2(original, path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                raise RuntimeError("source file changed during copy: " + relative)
            files[relative] = digest
    if git(source, "rev-parse", "HEAD").decode().strip() != commit or git(
            source, "diff", "--binary", "HEAD", "--") != patch:
        raise RuntimeError("dependency changed during snapshot; incomplete copy retained")
    manifest = {
        "schema": "starroboharness.dependency_snapshot.v1",
        "source": str(source), "commit": commit,
        "tracked_patch_sha256": hashlib.sha256(patch).hexdigest(),
        "files": files,
        "submodules": submodules,
        "symlinks": symlinks,
        "external_assets_not_frozen": external_assets,
        "omitted_untracked": [p.decode() for p in omitted.split(b"\0") if p],
        "scope": "tracked files only; ignored files and environment assets excluded",
    }
    receipt = destination / "unitypolicy-dependency.json"
    if receipt.exists():
        raise FileExistsError(receipt)
    receipt.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--recursive", action="store_true",
                        help="Freeze initialized submodules from local working copies")
    parser.add_argument("--allow-external-link", action="append", default=[],
                        help="Exact audited relative symlink; records but does not freeze target")
    args = parser.parse_args()
    manifest = freeze(args.source, args.destination, recursive=args.recursive,
                      external_links=args.allow_external_link)
    print(json.dumps({"snapshot": str(args.destination), "commit": manifest["commit"],
                      "files": len(manifest["files"]),
                      "omitted_untracked": manifest["omitted_untracked"]}))


if __name__ == "__main__":
    main()
