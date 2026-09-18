# Architecture

StarRoboHarness is not a unified model and does not replace a policy. It is the
execution and evaluation harness for reasoning-driven robotics that separates a
learned policy's proposal from the authority to execute it. The runtime owns
five boundaries:

1. **Observation** — `EnvironmentAdapter` returns an exact post-action state
   and native termination information.
2. **Proposal** — `PolicyAdapter` binds a candidate action or trajectory to that
   observation.
3. **Decision** — `ReasonerAdapter` or a gate assesses the previous execution
   and next proposal.
4. **Execution** — the evidence gate and robot-specific safety guard reject
   stale or unbounded decisions before the one authoritative executor sends an
   action.
5. **Trace** — `ChainedJsonlTrace` records observations, proposals, decisions,
   actual ACKs, outcomes, versions, latency, and cost references.

```text
observation ──▶ policy proposal ──▶ outcome/intent review
     ▲                                      │
     │                                      ▼
 actual ACK ◀── environment ◀── guard ◀── decision
```

## Dependency rule

`src/starroboharness` must not import StarVLA, OpenPI, RoboDojo, Isaac Sim, a model
provider SDK, or a cluster scheduler. Those systems live behind adapters or in
separate processes. This keeps `pip install star-robo-harness` lightweight and makes
the same control loop usable for VLA, WAM, diffusion, and classical policies.

## Identity and freshness

An observation gets a unique `observation_id`. Each proposal copies that ID and
gets a `proposal_id`. A reasoner decision carries the request ID issued for the
current review boundary. The runtime rejects any mismatch; it never guesses
that an old action chunk is still safe after the world changed.

## Gate semantics

The assessment answers two independent questions:

- What visibly happened during the last executed chunk?
- Does the next proposal pursue the correct current subgoal?

When implemented by the selected method profile, `edit` or `eef` is legal only
after an observed execution failure or a clearly misaligned next intent.
Uncertainty alone is not a takeover reason. A failed student action also does
not force takeover when a fresh proposal is visibly attempting a valid
recovery.

## Trace ownership

Large arrays and media stay in an artifact store and are referenced by digest.
The event trace is append-only and SHA-chained. Native success, partial score,
human adjudication, infrastructure failure, and budget censoring remain
separate fields.

## Reasoner variants

Method identity and implementation variant are separate. The current live
QwenPI_v3 integration is `compact_ephemeral_reviewer_v2`: every decision uses
a fresh structured Codex call, all 50 FK waypoints in a compact row encoding,
current and previous three-view RGB, bounded public memory, and EEF-only
corrections. It is intentionally labeled as not equivalent to GPT-as-Policy's
persistent full agent, which can keep workspace state, inspect files with
tools, and apply proposal-relative `edit` corrections.
