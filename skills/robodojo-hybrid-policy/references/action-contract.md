# RoboDojo dual-ARX-X5 action contract

Read this reference before issuing actions.

## Observation and proposal

- Cameras: head, left wrist, right wrist.
- Proprioception: 14D absolute joint state, left 7 values then right 7 values.
- Each arm contains six arm joints followed by one gripper opening.
- Native gripper opening is continuous: `0=closed`, `1=open`.
- A proposal must be bound to the latest observation and request ID.

## Modes

- `student`: execute 1–15 untouched steps from the fresh proposal.
- `edit`: execute 1–5 proposal steps plus per-arm translation and rotation
  residuals. Each arm is limited to 5 cm translation and 0.35 rad rotation.
  Gripper override is `keep`, `open`, or `closed`.
- `eef`: execute 1–5 steps toward explicit per-arm absolute EEF targets. Each
  target is within 5 cm and 0.35 rad of the measured current EEF; quaternions
  are unit `wxyz`; gripper state is an explicit boolean.
- `stop`: development-only unless the host explicitly permits non-native
  termination. It is not success or native failure.

EEF positions use the RoboDojo environment-origin frame and the `link6` pose.
The host recomputes bounded IK after actual control acknowledgements. Do not
reuse Panda, DROID, or another robot's geometry or gripper convention.

## Gate

An `edit` or `eef` decision requires either:

- visible evidence that the previous execution failed; or
- evidence that the fresh proposal pursues the wrong current subgoal.

Uncertainty alone is never sufficient. Every execute call requires a newly
inferred proposal after the latest observation.
