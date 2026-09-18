# Experimental live RoboDojo evaluation

The live runner is an integration reference, not a stable deployment API. It
connects a controller to externally managed simulator and policy workers and
records native terminal outcomes. The public contract below is intentionally
independent of any particular cluster, account, filesystem, or provider route.

## Frozen comparison

Freeze a panel containing explicit `case_id`, task, seed, and layout identity.
All methods must see the same cases. The current examples use the methods
`qwenpi_v3`, `qwenpi_v3_plus_gpt`, and `gpt_direct` where a three-way panel is
appropriate; development snapshots may use a documented method subset.

Native simulator termination and score are authoritative. An infrastructure
error means missing evidence, not a benchmark failure. Pending episodes have no
success-rate denominator.

## Execution contract

- The policy receives the instruction, three RGB camera views, and raw
  proprioception through an application-owned transport.
- The adapter validates proposal shape, freshness, action bounds, and gripper
  semantics before execution.
- A hybrid reviewer can inspect visible execution evidence and the next
  proposal, but not hidden object state, reward, or future simulator truth.
- One controller owns execution and records acknowledgements, public decisions,
  usage snapshots, and the native terminal receipt.
- Any uncertain acknowledgement is fail-closed. It must be retained as an
  attempt and never silently replaced by a best retry.

## Launch requirements

Provide a private runtime configuration containing simulator/policy endpoints,
source and checkpoint digests, a fresh output directory, and an authenticated
model route. Validate the configuration before the first simulator reset. Do
not commit that configuration when it contains operational identities or
credentials.

## Evidence and publication

Each attempt should retain machine-readable outcome, progress, and error files;
public decision/tool records; and usage snapshots. Raw frames, trajectories,
RPC streams, and videos belong in a private artifact store. The public release
should report method identity, valid coverage, score, latency, and rounded
usage with clear attribution limits.
