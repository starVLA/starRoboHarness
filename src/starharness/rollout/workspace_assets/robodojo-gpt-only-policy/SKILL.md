---
name: robodojo-gpt-only-rollout
description: Control one RoboDojo episode with bounded dual-arm EEF actions.
---

# RoboDojo GPT-only policy

Read `context/teacher_context.md` and `context/eef_control.md`. Use bounded EEF
targets for both arms, verify each post-action observation, and continue until
native termination. Do not reset, replay uncertain acknowledgements, query
hidden state/reward, or open a second control connection.
