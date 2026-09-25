# Public RoboDojo policy context

Use the original task instruction, three RGB views, measured proprioception,
student proposals, and exact post-acknowledgement observations. Do not infer
hidden object state, reward, or future simulator truth.

Derive objectives from the current native instruction and task_context.json.
The learned policy is QwenPI_v3, not the upstream pi05 checkpoint. Workspace
parity is not a claim of identical policy knowledge or performance. Prior-run
scores, hidden object identities and evaluator internals are not planning inputs.

Use workspace.json for exact history, observations, proposals and diagnostics
paths. Reopen original-resolution RGB for fine details; teacher previews do not
change the student's images. Keep crops/calculations in scratch/ and durable
visible-state memory in NOTES.md. Do not edit host-owned records or source.

For category tasks only, maintain category-ledger.json from observed instances:
category, instructed destination, stable instance IDs, pending/held/
released-unverified/verified-contained states, and evidence frame/step. Do not
invent a fixed number of objects, class names or basket mapping. Prefer completing
the active category; when the horizon is short prioritize the category nearest
completion. Switch only after completion or a documented obstacle/replanning
reason. A blocked category must not force unsafe motion or endless corrections.
Verify containment after release and withdrawal, and revoke it after a slip.
The ledger is a model hypothesis, not an oracle or native success signal.

When task_context requires arm return, reserve steps for safe withdrawal and
return near the episode-start EEF positions and orientations. Make Kong uses
its tile sequence instead; do not infer that arm return is its missing goal.
Continue until rollout_finished, including when the native result is failure.

Public assessments, working notes and reports use English and concise visible
evidence, not private chain-of-thought. Preserve the original task instruction.
