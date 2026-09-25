---
name: robodojo-gpt-only-policy
description: Safely control one RoboDojo dual-arm episode with bounded EEF actions.
---

# RoboDojo GPT-only policy

Use the original task instruction, the three current RGB views, measured
proprioception, and exact post-acknowledgement observations. Choose bounded EEF
targets for both arms. A target or gripper command is not proof of arrival,
grasp, or release; verify visible motion before continuing.

Do not use hidden scene state, reward, future simulator truth, rollback, a second
control connection, or replay after an uncertain acknowledgement. Continue until
the native simulator reports termination. Keep public notes evidence-based and
never expose private chain-of-thought.

See the injected `context/eef_control.md` and generated `AGENTS.md` for the
robot contract and workspace boundary.
