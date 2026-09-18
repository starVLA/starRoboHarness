# QwenPI_v3 RoboDojo contract

Read this reference only when the student policy is QwenPI_v3.

- Model family: Qwen3-VL-4B with a 36-layer layer-wise flow-matching action
  head and per-layer projection to a 1024D Action DiT.
- Inputs: current head, left-wrist, and right-wrist RGB images in that order,
  resized to 224×224; original instruction; raw 14D absolute-joint state.
- State is discretized into instruction tokens by QwenPI_v3.
- Output: 50×14 absolute joint-position actions.
- Normalization: the serving layer must apply the checkpoint's `arx_x5` q99
  statistics before StarRoboHarness sees executable actions.
- Current native deployment executes 16 actions before replanning. A hybrid
  reviewer may choose a shorter 1–15 step student prefix.
- The XPolicyLab adapter accepts `num_ddim_steps=10`, but the current
  QwenPI_v3 `predict_action()` path does not consume it. The effective action
  sampler uses `num_inference_timesteps=4` from the checkpoint config.

The validated 2026-09-16 runtime requires both the current StarVLA interleaved
LayerwiseFM forward and training-time q99 state normalization in the model
server. The old vendored runtime normalizes state but runs the legacy all-cross
forward; the unpatched current runtime uses the right forward but passes raw
state to QwenPI_v3. Either mismatch can collapse performance.

Reject normalized actions, missing camera views, wrong state/action ordering,
wrong horizon or dimensions, non-finite values, and gripper openings outside
`[0,1]`. Do not silently clip joint values or reinterpret abs-qpos as EEF deltas.
