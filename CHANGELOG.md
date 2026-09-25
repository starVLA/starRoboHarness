# Changelog

All notable project changes are recorded here. starRoboHarness uses development
pre-releases until the native evaluation protocol and public adapter APIs are
stable.

## Unreleased

- Rebranded the public runtime as starRoboHarness, with `starharness` as the Python
  package and `starharness.core` as the model-neutral public contract surface.
- Rewrote the README and project vision around Robot-as-Policy execution,
  reasoner supervision/direct control, skills, traceability, and evaluation.
- Preserved frozen panel schemas and historical UnityPolicy paths where changing
  them would invalidate existing experiment identities.

- Retained the completed Astra Direct off-panel timeout and its usage evidence.
- Added method-subset campaigns and a frozen four-task, five-case, paired
  StarVLA / StarVLA+Astra panel (40 planned native terminal episodes).
- Added a fail-closed manual tmux launcher and dynamic two- or three-method
  reporting/monitoring.
- Added structured public decision-record export while retaining raw app-server,
  tool, usage, policy, control, and native-outcome evidence. Private hidden
  chain-of-thought is explicitly not claimed as an artifact.
- Added a task-scoped cream web dashboard whose camera, policy summary,
  infrastructure evidence, and public GPT decision timeline stay pinned to the
  user's selected RoboDojo task.
- Added replay controls for retained camera frames and read-only cross-resume
  evidence roots, so accepted historical decisions remain visible in a fresh
  recovery campaign.
- Serialized Kubernetes port-forward startup and added bounded pre-control
  retries with per-attempt receipts; post-control failures remain fail-closed
  and are never silently replayed.
- Added receipt-based recovery for terminal native results that were stranded by
  an outer read timeout, plus explicit lineage for excluded or orphaned control
  attempts so recovery campaigns never silently replay uncertain actions.
- Clarified the terminal monitor's mixed active/error section so a healthy
  first decision is not presented as an error.

## 0.1.0-alpha.1 — 2026-09-17

First collaborative development snapshot.

### Added

- Model-, policy-, and environment-neutral proposal/review/execution contracts.
- QwenPI_v3 adapter and StarVLA policy-service bridge with explicit checkpoint,
  action-space, gripper, and state-normalization identities.
- Persistent GPT-6 Astra `xhigh` backend for hybrid and direct RoboDojo control.
- Native-result accounting that separates success, partial score, timeout,
  incomplete smoke runs, infrastructure failure, and interrupted control.
- Frozen five-task panel, dependency manifests, runtime identity receipts,
  supervisor state, resume guards, and development/result dashboards.
- Versioned RoboDojo hybrid-policy skill and contributor/research documentation.

### Development evidence

- QwenPI_v3: one valid off-panel `build_tower/layout5` timeout, Score 10/100.
- Astra + QwenPI: one valid off-panel native success, Score 100/100.
- QwenPI fixed-15 cadence ablation: one valid timeout, Score 0/100.
- Astra Direct: still running at snapshot time; no terminal result is claimed.

These are retained development episodes, not a formal success-rate estimate.
See the [iteration record](docs/iterations/2026-09-17-v0.1.0-alpha.1.md) for
method and attribution caveats.

### Known limitations

- The formal 75-episode campaign has not started.
- The hybrid success recorded zero GPT correction steps; dynamic review cadence
  and non-bitwise-identical observations prevent a causal GPT-benefit claim.
- Raw simulator artifacts and external checkpoints are intentionally not
  committed to Git.
- The live rollout API remains experimental.
