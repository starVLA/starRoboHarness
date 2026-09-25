# Development environments

starRoboHarness separates the lightweight controller from the simulator and policy
workers. The public repository documents interfaces only; site-specific
cluster names, mounts, credentials, and launch addresses belong in a private
operator runbook.

## Environment separation

Keep these roles distinct:

- RoboDojo/Isaac simulation;
- StarVLA or OpenPI policy inference;
- the starRoboHarness controller, tests, and evidence collector.

Every evaluation receives a unique run ID, output directory, port allocation,
and explicit policy/simulator identity. A transport or physics error is an
infrastructure outcome, not permission to turn an uncertain episode into a
zero-score benchmark result.

## Before publishing

Run the unit, contract, and replay suites; record the source revision and
checkpoint digest in a private manifest; and confirm that each published row
has a complete native terminal receipt. Keep checkpoints, trajectories, raw
RPC streams, credentials, account identifiers, absolute paths, and cluster
metadata outside Git.

## Handoff checklist

1. Freeze the panel and method identity before allocating simulators.
2. Write a receipt for every attempt, including invalid and interrupted ones.
3. Report valid coverage separately from success and score.
4. Keep raw evidence in an access-controlled artifact store.
5. Publish only the smallest redacted summary needed for review.
