# Dual-arm EEF control context

The RoboDojo dual-ARX-X5 contract uses head, left-wrist, and right-wrist RGB
views plus a 14-value absolute joint state. EEF poses use the environment-origin
frame and `link6`, with unit `wxyz` quaternions. Gripper opening is continuous:
zero is closed and one is open.

Student prefixes and corrections are bounded by the injected action contract.
Recompute from the latest acknowledged observation. A gripper command or IK
target is not proof of grasp, placement, or release; verify motion and
containment in a fresh observation.
