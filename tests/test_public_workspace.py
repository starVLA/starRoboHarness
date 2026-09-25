import hashlib
import json

import pytest

from starharness.rollout.public_workspace import prepare_public_workspace


def test_public_workspace_replicates_upstream_contract(tmp_path):
    audit = tmp_path / "episode"
    audit.mkdir()
    agent = prepare_public_workspace(audit)
    assert (agent / "AGENTS.md").is_file()
    assert (agent / "NOTES.md").is_file()
    assert (agent / "context/teacher_context.md").is_file()
    assert (agent / "context/eef_control.md").is_file()
    assert (agent / ".agents/skills/robodojo-hybrid-rollout/SKILL.md").is_file()
    manifest = json.loads((agent / "workspace.json").read_text())
    assert manifest["schema"] == "starharness.agent_workspace.v2"
    assert manifest["evaluation_method"] == "qwenpi_v3_plus_gpt"
    assert manifest["baseline_full_conversation_available"] is False
    assert manifest["context_files"]["context/teacher_context.md"]


def test_direct_workspace_omits_student_proposals(tmp_path):
    audit = tmp_path / "episode"
    audit.mkdir()
    agent = prepare_public_workspace(audit, direct=True)
    manifest = json.loads((agent / "workspace.json").read_text())
    assert manifest["evaluation_method"] == "gpt_only"
    assert manifest["proposals_path"] is None
    assert (agent / ".agents/skills/robodojo-gpt-only-rollout/SKILL.md").is_file()


@pytest.mark.parametrize("direct", [False, True])
def test_every_packaged_resource_is_recorded_and_discoverable(tmp_path, direct):
    tmp_path.joinpath("audit").mkdir()
    agent = prepare_public_workspace(
        tmp_path / "audit", direct=direct, task="classify_objects_by_language"
    )
    manifest = json.loads((agent / "workspace.json").read_text())
    for relative, digest in manifest["resource_files"].items():
        assert hashlib.sha256((agent / relative).read_bytes()).hexdigest() == digest
    skill = next((agent / ".agents/skills").iterdir())
    for name in ("teacher_context.md", "eef_control.md", "task_context.json"):
        assert (skill / "context" / name).read_bytes() == (agent / "context" / name).read_bytes()
    assert (skill / "SKILL.md").read_bytes() == (agent / "SKILL.md").read_bytes()
    assert (agent / "gate_prompt.md").exists() is (not direct)
    assert "category_completion" in json.loads((agent / "context/task_context.json").read_text())


def test_fresh_workspace_never_overwrites_episode_memory(tmp_path):
    agent = prepare_public_workspace(tmp_path, task="arrange_largest_number")
    notes = agent / "NOTES.md"
    notes.write_text("observed progress")
    with pytest.raises(FileExistsError):
        prepare_public_workspace(tmp_path)
    assert notes.read_text() == "observed progress"
    assert "category_completion" not in json.loads(
        (agent / "context/task_context.json").read_text()
    )
