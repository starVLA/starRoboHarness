# Dual-arm EEF control context

RoboDojo uses head, left-wrist, and right-wrist RGB views plus a 14-value
absolute joint state. EEF poses use the environment-origin frame and link6,
with unit wxyz quaternions. Gripper opening is continuous: zero closed, one
open. A command or IK target is not proof of grasp or release; verify it from a
fresh observation.

Action/proprio order is left joints 1..6, left opening, right joints 1..6,
right opening. Arm joints and EEF poses are measured; gripper proprio is the
last commanded opening, not a measured finger gap. Do not apply Panda/DROID
geometry or an assumed fingertip offset axis to link6.

Hybrid inference returns H50 absolute joint targets and both-arm robot-only FK.
Student execution uses 1–15 unmodified steps; discard the unused suffix and
infer again from the new observation. FK predicts kinematics, not contact,
object motion or future task success.

Proposal-relative edit and absolute eef recovery execute 1–5 steps. Per arm,
translation is bounded to 0.05 m and rotation to 0.35 rad. Absolute targets
specify both left and right position/quaternion_wxyz/gripper_closed. To hold
an arm, use its measured pose and intended opening. A zero/keep edit preserves
that arm's student trajectory; it does not freeze it. Keep preserves continuous
student opening. Local damped-least-squares IK is recomputed after every real
control ACK; requested targets are not proof of arrival.

Observe the whole grasp–lift–transport–release sequence. Clear container rims
with the object and fingers before lateral transport, release inside the opening,
then withdraw vertically before lateral motion. Choose clearance from RGB,
not hidden geometry. If repeated corrections produce no visible object motion,
record the failure, reassess geometry and choose a distinct bounded recovery;
do not just repeat the same target. Never relax host limits to escape a stall.

Control dt is 0.04 s; the simulator owns interpolation and physics substeps.
Use recorded blocking tools only: no alternate socket, teleportation, rollback,
reset, object-aware planner, reward query or hypothetical contact simulation.
