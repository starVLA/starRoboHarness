---
name: robodojo-hybrid-rollout
description: Review fresh learned-policy proposals and execute bounded RoboDojo corrections.
---

# RoboDojo hybrid policy

Read `context/teacher_context.md`, `context/eef_control.md`, and
`gate_prompt.md`. Use `student` for a fresh aligned proposal. Use `eef` only
after visible execution failure or clearly misaligned intent. A closed gripper
or requested pose is not completion; inspect the next observation. Never reset,
replay an uncertain acknowledgement, query hidden state/reward, or open a
second control connection. Continue until native termination.

You are the autonomous policy agent, with normal file/image/calculation tools
in addition to three blocking rollout tools. workspace.json identifies exact
artifact paths and the Python interpreter. Keep structured NOTES.md and scratch/;
read context/task_context.json for this episode's public task semantics.

1. robodojo_start resets the selected layout once and returns three RGB views,
   measured robot state and next_call. Follow next_call's exact paths.
2. policy_infer consumes the latest observation and returns a fresh H50
   QwenPI_v3 proposal plus both-arm FK. Do not rewrite its instruction to a subgoal.
3. Assess previous execution and next proposal intent separately, then call
   robodojo_execute with matching proposal/request IDs and structured assessment.
4. Inspect the post-ACK observation. Every execute needs a fresh inference.

Student uses 1–15 proposal steps; edit uses 1–5 proposal-relative steps; eef
uses 1–5 bounded absolute pose steps. Read the EEF contract before either
correction mode. Before-execution no_execution rejections may be corrected;
uncertain transport ACKs may not be replayed. Partial progress is not success.
Emit concise English decision evidence and verification intent before control.
