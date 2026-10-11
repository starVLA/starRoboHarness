# Repository layout and boundaries

The repository is organized around stable contracts and replaceable integrations. The structure follows the useful parts of large embodied-AI infrastructures such as RLinf and RPent: a small core, explicit backends, runnable examples, versioned manifests, operational tools, and documentation that explains how evidence is produced.

## Canonical areas

| Area | Purpose | What belongs here |
| --- | --- | --- |
| `src/starharness/core` | Stable public contracts | Observation, proposal, decision, execution, receipt, and error types. |
| `src/starharness/adapters` | Policy and environment boundaries | Thin adapters that translate native APIs into the contracts. |
| `src/starharness/reasoners` | Reasoner transports | Provider clients and bounded decision interfaces. |
| `src/starharness/rollout` | Episode lifecycle | Freshness, ownership, recovery, persistence, and native result handling. |
| `configs/` | Reproducible inputs | Frozen panels, runtime manifests, and protocol versions. |
| `scripts/` | Operations | Preflight, launch, queue, audit, merge, and report commands. |
| `examples/` | Learning path | Small examples that run without a simulator where possible. |
| `tests/` | Observable contracts | Unit and integration tests for invariants and compatibility. |
| `assets/` | Publication and branding | Teaser, framework, logos, and release-safe visuals. |
| `exps/` | Paper production | LaTeX, tables, editable figures, and source-backed evidence notes. |
| `UI/` | Read-only monitoring | Local dashboard assets and collector. |

## Simulation and real robot code

Simulation code belongs in backend-specific adapters and launchers. Real-robot code belongs in a separate adapter namespace and must not import simulator modules. Both implement the same policy proposal and execution contracts. Shared code is limited to message schemas, validation, receipts, and provider-neutral utilities.

A new backend should add:

1. a native-to-harness adapter;
2. a versioned configuration or task manifest;
3. a preflight command that checks dependencies and action semantics;
4. a contract test with a fake or dry-run backend;
5. a receipt/report writer that preserves native outcomes and failure classes.

## Evidence boundary

`artifacts/`, `outputs/`, checkpoints, simulator installations, private logs, and credentials are runtime data. They remain outside the public source tree. A release may include small, sanitized JSON summaries and checksums under `docs/` or `assets/`, but a raw rollout bundle belongs in the private evidence store.

## Deprecation rule

Do not delete an integration merely because it is not in the default quick start. Mark it with a protocol owner and migration note, move one-off campaign code under a dated archive, and delete only after its receipts and replacement path are documented. This keeps the paper evidence auditable while reducing the active surface.
