"""Bind the persistent reasoner and native rollout tools for one episode."""

import json
from pathlib import Path

from hybrid_rollout.robodojo.robodojo_server.gate_assessment import GATE_INSTRUCTION

from .persistent_agent import PersistentAgent
from .persistent_tools import DirectTools, QwenPITools
from .student import QwenPIStudent

PROMPT = """Control one RoboDojo dual ARX X5 episode as an autonomous policy agent.
Use the supplied blocking rollout tools to control the robot. Native shell/image
tools are for inspecting this episode's recorded RGB, proprioception, proposals,
and execution files. Maintain NOTES.md and scratch/ in your workspace. Do not
modify host evidence, open a second control connection, query hidden scene state,
reset again, or use hypothetical physics. Derive goals from the native instruction.
Use English for public explanations and concise visible evidence; never reveal
private chain-of-thought. Every tool's next_call supplies exact paths and order.
Before each control-changing tool call, emit a concise public decision record
with: observed evidence, immediate subgoal, chosen action source/range, expected
outcome, uncertainty or risk, and the next verification. This auditable record
is not private chain-of-thought. Keep NOTES.md current across the episode.

Three views are head, left wrist, right wrist. Compare before/after observations.
EEF means measured link6 in shared environment-origin coordinates, meters, unit
wxyz quaternion. Both arms must be explicit. Native gripper opening is continuous
0=closed, 1=open; gripper_closed=true commands zero. A gripper command does not
prove grasp and an IK target does not prove arrival. No Panda/DROID pad offset
applies. Estimate contact geometry from observations, using crops when needed.
Clear container rims before lateral motion, verify lift, release and withdraw.
If task_context requires arm return, reserve time to return both arms near their
episode-start EEF poses after completing the object task. Do not confuse visible
partial progress with native success. Continue until rollout_finished=true.

EEF recovery executes 1-5 steps with <=0.05m translation and <=0.35rad rotation
from measured poses, recomputing robot-only IK after each actual ACK. Inspect
actual motion and correct from the latest observation. Validation rejections
with no_execution=true may be corrected; never replay an uncertain action.
"""
HYBRID = """
The student is QwenPI_v3, served by StarVLA/PyTorch, not pi05/OpenPI. Its original
instruction and normalized model input contract are preserved by the host.
Call policy_infer once per fresh observation, inspect all 50 proposal FK steps,
then robodojo_execute. FK predicts robot kinematics, not future object outcomes.
student executes 1-15 unchanged proposal steps. edit applies 1-5 proposal-relative
steps with per-arm delta_position, delta_rotation_vector, and gripper keep/open/closed.
Offsets are bounded to 0.05m/0.35rad. Zero/keep preserves student motion rather
than freezing the arm. eef is absolute bounded recovery. Hand back when aligned.
The following outcome/intent gate is mandatory:
"""


def run_persistent(*, root, method, case, config, connection, sim_port, runtime_identity):
    root = Path(root)
    direct = method == "gpt_direct"
    prompt = PROMPT + ("\nNo student policy exists. Use robodojo_act with EEF only."
                       if direct else HYBRID + GATE_INSTRUCTION)
    provider = config["codex_provider"]
    worker = PersistentAgent(
        root / "reasoner", config["codex"], prompt=prompt, provider=provider, direct=direct,
        no_action_seconds=config.get("no_action_seconds", 600),
        no_action_tokens=config.get("no_action_tokens", 250000))
    rollout = None
    try:
        output = root / "controller"
        output.mkdir()
        kwargs = dict(provider=provider, sim_port=sim_port, seed=case["layout_id"],
                      max_decisions=config.get("smoke_decisions", 0),
                      prompt_sha256=worker.prompt_sha256)
        rollout = (DirectTools(output, case["runtime_task"], **kwargs) if direct else
                   QwenPITools(output, case["runtime_task"],
                                QwenPIStudent(connection, runtime_identity), **kwargs))
        worker.run(rollout)
        return json.loads((output / "result.json").read_text())
    except BaseException:
        if rollout is not None and rollout.episode is not None and rollout.phase != "done":
            try:
                rollout.finish("controller_error")
            except Exception:
                pass
        raise
    finally:
        worker.close()
        if rollout is not None:
            rollout.close()
