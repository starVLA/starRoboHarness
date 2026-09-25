# Portable deployment

1. Run `bash scripts/bootstrap.sh` with Python 3.10+ (`PYTHON_BIN` overrides the executable).
2. Install RoboDojo/Isaac and StarVLA in separate environments following upstream requirements. Provision and hash the checkpoint/base VLM independently.
3. Create ignored `local/`, copy `configs/runtime/local_robodojo_starvla.json` to `local/runtime.json`, and replace every path, GPU, port and identity hash. Relative paths resolve against the repository root, not the configuration directory. Prefer absolute paths in this private file.
4. Run the README preflight with a fresh output directory. Pure Policy does not consume reasoner quota.
5. Smoke-test with `--smoke qwenpi_v3 --smoke-decisions 2` instead of `--preflight`, using another fresh output directory. A decision-limited smoke is not benchmark evidence.
6. Run your frozen panel with `--method qwenpi_v3` or `--method qwenpi_v3_plus_gpt`, without smoke/preflight flags. Preserve all outputs.

Preflight does not replace live smoke. The bootstrap cannot install cluster drivers, gated datasets, external weights or credentials automatically.

## Cluster operation

Start one worker per host with unique ports and output roots. Scale independent cases only after proving readiness and cleanup. Never let two controllers own one episode. Keep policy, simulator and controller Python environments separate.

`python -m starharness.rollout.baseline_queue --help` exposes the same-node baseline queue. It uses the campaign schema, **not** the local runner configuration above. It requires verified source/checkpoint manifests and the frozen 16-step pure-policy cadence; inspect its preflight requirements before adapting a cluster launcher.

Use a scheduler or tmux for long runs. Heartbeat/state files require atomic replacement: object-store mounts may not support it. Use object storage for immutable exports. A slow status read does not prove a dead worker; inspect process identity before recovery.

## Private operator manifest (outside Git)

Carry source/runtime/checkpoint/normalization/panel/method hashes, Python executables, device and endpoint mappings, run roots, process identities and artifact restoration instructions. Keep credentials separately in a secret manager. Repeat preflight and smoke after migration; verify image order, units, action shape, normalization, gripper direction and executed horizon.
