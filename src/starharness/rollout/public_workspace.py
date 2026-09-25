"""Packaged, episode-local workspace adapted from GPT-as-Policy's contract.

Generated manifests contain private runtime paths; they are evidence, not
publication artifacts. Only maintained public templates are bundled here.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from hybrid_rollout.robodojo.prompt_context import CONTEXT_VERSION, task_context
from hybrid_rollout.robodojo.robodojo_server.gate_assessment import GATE_INSTRUCTION

ASSETS = Path(__file__).with_name("workspace_assets")
WORKSPACE_VERSION = "starharness.agent_workspace.v2"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare_public_workspace(audit: str | Path, *, direct: bool = False,
                             task: str | None = None) -> Path:
    """Prepare a fresh workspace; never overwrite a prior episode's memory."""
    audit = Path(audit).resolve()
    if not audit.is_dir():
        raise FileNotFoundError(f"episode audit directory does not exist: {audit}")
    agent = audit / "agent"
    agent.mkdir()
    (agent / "scratch").mkdir()
    context = agent / "context"
    shutil.copytree(ASSETS / "context", context)
    name = "robodojo-gpt-only-rollout" if direct else "robodojo-hybrid-rollout"
    asset_name = "robodojo-gpt-only-policy" if direct else "robodojo-hybrid-policy"
    skill = agent / ".agents" / "skills" / name
    skill.mkdir(parents=True)
    shutil.copy2(ASSETS / asset_name / "SKILL.md", agent / "SKILL.md")
    shutil.copy2(agent / "SKILL.md", skill / "SKILL.md")
    if not direct:
        # One authoritative gate, identical in the prompt and discoverable file.
        (agent / "gate_prompt.md").write_text(GATE_INSTRUCTION, encoding="utf-8")
        shutil.copy2(agent / "gate_prompt.md", skill / "gate_prompt.md")
    guidance = task_context(task) if task else {}
    _write_json(context / "task_context.json", guidance)
    shutil.copytree(context, skill / "context")
    shutil.copy2(ASSETS / "NOTES.md", agent / "NOTES.md")
    _write_json(agent / "category-ledger.json", {
        "schema": "starharness.visible_category_ledger.v1",
        "observation_step": None, "active_category": None,
        "switch_reason": None, "categories": [],
    })
    (agent / "AGENTS.md").write_text(
        "# Episode workspace\n\n"
        "Your cwd is this directory. Read SKILL.md, workspace.json and "
        "context/teacher_context.md; read context/eef_control.md before acting. "
        "Read context/task_context.json for this task only. "
        + ("No student policy or proposal gate exists in direct mode. "
           if direct else "Read gate_prompt.md for the unchanged outcome/intent gate. ")
        + "Maintain NOTES.md and, for category tasks, category-ledger.json. "
        "Use normal shell/image/calculation tools to inspect recorded RGB, "
        "proprioception and robot-only FK; use scratch/ for crops and calculations. "
        "Use only the blocking rollout tools for control. Never reset twice, "
        "replay uncertain ACKs, query hidden scene state/reward, open a second "
        "control connection, or change host-owned evidence. "
        "The ledger is a visual hypothesis, not ground truth or native success.\n",
        encoding="utf-8",
    )
    # reasoner/ and controller/ are siblings under the episode root.
    controller = audit.parent / "controller"
    workspace = {
        "schema": WORKSPACE_VERSION,
        "evaluation_method": "gpt_only" if direct else "qwenpi_v3_plus_gpt",
        "task": task, "context_version": CONTEXT_VERSION,
        "controller_output": str(controller),
        "source_root": str(Path(__file__).resolve().parents[2]),
        "python_executable": sys.executable, "robot_profile": "robodojo",
        "history_path": str(controller / "history.json"),
        "observations_path": str(controller / "observations"),
        "execution_files": str(controller / "execution_NNN.npz"),
        "eef_diagnostics_files": str(controller / "edit_NNN.json"),
        "scratch": str(agent / "scratch"), "notes_path": str(agent / "NOTES.md"),
        "ledger_path": str(agent / "category-ledger.json"),
        "baseline_full_conversation_available": False,
        "category_priority_enforcement": "model_guidance_not_visual_ground_truth",
        "context_files": {
            str(p.relative_to(agent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(context.rglob("*")) if p.is_file()
        },
        "resource_files": {
            str(p.relative_to(agent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(agent.rglob("*")) if p.is_file()
        },
    }
    workspace["proposals_path"] = None if direct else str(controller / "proposals")
    _write_json(agent / "workspace.json", workspace)
    return agent
