---
name: robodojo-hybrid-policy
description: Review and safely execute fresh robot-policy proposals in one authorized RoboDojo dual-ARX-X5 episode, including QwenPI_v3 proposals. Use for hybrid reasoning-policy rollouts, not training or offline leaderboard interpretation.
---

# RoboDojo hybrid policy

Review one authorized episode using the capabilities the host explicitly
provides. A full-agent host may expose persistent notes and blocking rollout
tools. A compact host may instead provide one structured decision request with
no tools and no persistent session. Never claim that the compact variant is a
faithful GPT-as-Policy full-agent reproduction.

Before reporting or comparing results, read the run's `method-profile.json`.
The `compact_ephemeral_reviewer_v2` profile sees current and previous three-view
RGB, a compact encoding of every policy waypoint, bounded public memory, and
EEF corrections only. It does not support proposal-residual `edit` actions.

Before controlling the episode, read [the action contract](references/action-contract.md).
When `policy_id=qwenpi_v3`, also read [the QwenPI_v3 contract](references/qwenpi-v3.md).
When launching, recovering, or reporting a multi-episode formal campaign, read
[the formal evaluation recovery contract](references/formal-evaluation-recovery.md).

## Loop

1. Start once and preserve the original task instruction.
2. Request one fresh proposal from the latest observation.
3. Assess the last executed chunk and the next proposal as separate questions.
4. Execute a student prefix or a correction supported by the host profile.
5. Inspect the exact post-ACK observation and repeat until native termination.

Maintain `verified_completed`, `currently_attempting`, and `remaining` from
visible evidence. Revoke a completed item if later observations show that it
was lost. Infer proposal intent only from its robot trajectory and gripper
sequence; do not claim access to the policy's internal intention.

Take over only after an observed execution failure or a clearly misaligned next
intent. Uncertainty, an imperfect-looking pose, or low expected success is not
enough. Prefer student recovery and hand back once the proposal is aligned.

Do not use reward, object truth, future simulated object state, rollback,
mid-episode reset, proposal replay, or a second control connection. A gripper
command does not prove grasp or release. At native completion, report the
outcome and artifact paths without turning partial score into success.
