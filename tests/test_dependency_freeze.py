import shutil

import pytest

from starroboharness.rollout.freeze_dependency import freeze, git


def test_snapshot_keeps_commit_and_dirty_code_without_modifying_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Snapshot test")
    (source / "model.py").write_text("original\n")
    (source / "deleted.py").write_text("old\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "initial")
    (source / "model.py").write_text("corrected\n")
    (source / "deleted.py").unlink()
    (source / "notes.txt").write_text("not executable evidence\n")
    (source / "added.py").write_text("new tracked code\n")
    git(source, "add", "added.py")
    (source / "internal").symlink_to("added.py")
    git(source, "add", "internal")
    before = git(source, "status", "--porcelain")
    target = tmp_path / "snapshot"
    result = freeze(source, target)
    assert git(source, "status", "--porcelain") == before
    assert git(target, "rev-parse", "HEAD") == git(source, "rev-parse", "HEAD")
    assert (target / "model.py").read_text() == "corrected\n"
    assert not (target / "deleted.py").exists()
    assert result["omitted_untracked"] == ["notes.txt"]
    assert set(result["files"]) == {"model.py", "added.py"}
    assert result["symlinks"] == {"internal": "added.py"}
    (source / "model.py").write_text("later edit\n")
    assert (target / "model.py").read_text() == "corrected\n"
    with pytest.raises(FileExistsError):
        freeze(source, target)
    (source / "external").symlink_to(tmp_path / "outside-dataset")
    git(source, "add", "external")
    with pytest.raises(ValueError, match="external dependency symlink"):
        freeze(source, tmp_path / "reject-external")
    audited = freeze(source, tmp_path / "audited-external", external_links=["external"])
    assert audited["external_assets_not_frozen"] == {
        "external": str(tmp_path / "outside-dataset")}


def test_recursive_snapshot_uses_local_submodule_working_changes(tmp_path):
    child, parent = tmp_path / "child", tmp_path / "parent"
    for source in (child, parent):
        source.mkdir()
        git(source, "init")
        git(source, "config", "user.email", "test@example.invalid")
        git(source, "config", "user.name", "Snapshot test")
        (source / "code.py").write_text("initial\n")
        git(source, "add", ".")
        git(source, "commit", "-m", "initial")
    git(parent, "-c", "protocol.file.allow=always", "submodule", "add", str(child), "nested")
    git(parent, "commit", "-am", "submodule")
    (parent / "nested/code.py").write_text("patched\n")
    with pytest.raises(ValueError, match="submodule"):
        freeze(parent, tmp_path / "nonrecursive")
    manifest = freeze(parent, tmp_path / "recursive", recursive=True)
    assert (tmp_path / "recursive/nested/code.py").read_text() == "patched\n"
    assert "nested" in manifest["submodules"]


@pytest.mark.skipif(shutil.which("git-lfs") is None, reason="Git LFS unavailable")
def test_lfs_snapshot_copies_installed_bytes_without_downloading(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Snapshot test")
    git(source, "lfs", "install", "--local")
    git(source, "lfs", "track", "*.bin")
    payload = b"installed asset bytes\x00" * 20
    (source / "asset.bin").write_bytes(payload)
    git(source, "add", ".")
    git(source, "commit", "-m", "lfs asset")
    assert git(source, "show", "HEAD:asset.bin").startswith(b"version https://git-lfs")
    target = tmp_path / "frozen"
    freeze(source, target)
    assert (target / "asset.bin").read_bytes() == payload
