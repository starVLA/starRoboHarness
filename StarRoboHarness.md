# StarRoboHarness

> Connect frontier multimodal reasoners to arbitrary robot policies through a
> small, auditable, efficient, and benchmark-neutral control layer.

StarRoboHarness is not a unified model and does not replace a policy. It is an open
execution, orchestration, and evaluation harness for reasoning-driven robotics:
policies propose, reasoners supervise or act, skills mediate reusable abilities,
and robots/environments provide observations and real execution outcomes.

The public runtime is organized around `Observation → Proposal → Decision →
Execution → Trace`, with evaluation consuming the same trace rather than
reconstructing results from an opaque runner.

Last updated: 2026-09-19

## Motivation

Two mature implementation lines motivate the project:

- GPT-as-Policy demonstrates GPT-6 Astra as a direct embodied policy and as a
  reviewer that selectively corrects π0.5 proposals.
- QwenPI_v3 combines Qwen3-VL-4B with a layer-wise cross-DiT flow-matching
  action head and has a maintained RoboDojo deployment.

Published numbers from these projects use different evaluation protocols. The
GPT-as-Policy report uses a 10-task, five-case-per-task aligned panel; StarVLA's
published QwenPI_v3 table uses 42 tasks and 50 episodes per task. They are not
directly comparable. StarRoboHarness first establishes same-task, same-layout,
same-seed paired evaluation.

## Goals

- Improve QwenPI_v3 success and native score with selective, bounded reasoning
  intervention.
- Improve direct reasoner control and the hybrid protocol rather than copying
  one fixed prompt.
- Treat quality and efficiency as joint objectives: calls, tokens, cache use,
  latency, correction ratio, and GPU-hours accompany success metrics.
- Make reasoners, policies, robots, and benchmarks replaceable through small
  adapters.
- Remain simple enough for an external contributor to add an adapter without
  installing every simulator and model runtime.

## Non-goals for the first release

- Vendoring GPT-as-Policy, StarVLA, RoboDojo, or checkpoints.
- Retraining QwenPI_v3 before the inference/control baseline is trustworthy.
- Using reward, object truth, future simulator state, hidden action scripts, or
  case-specific answers as reasoner context.
- Calling every model output a success or using an expensive reasoner on every
  control step.

## Principles

1. Protocols are stable; models are replaceable.
2. Only the environment adapter can change environment state.
3. Every proposal is bound to one exact observation.
4. Correction requires observed failure or misaligned next intent.
5. Uncertainty alone never authorizes takeover.
6. Use the smallest correction and return control when the student recovers.
7. Preserve the benchmark's original task instruction.
8. Record proposals, decisions, actual ACKs, native outcomes, versions, cost,
   and latency in an append-only trace.
9. Keep method identity independent of credentials and provider routing.
10. Parallelize cases, never concurrent control connections to one episode.

## Architecture

```text
task + observation ──▶ ContextCompiler ──▶ ReasonerAdapter
          │                                      │
          ▼                                      ▼
   PolicyAdapter ── proposal ──▶ evidence gate + SafetyGuard
                                                 │
                                                 ▼
                                     EnvironmentAdapter
                                                 │
                                                 ▼
                              trace + metrics + native outcome
```

The core package knows only observations, proposals, decisions, execution
results, and traces. StarVLA, OpenPI, Isaac Sim, and model-provider clients stay
outside the core process.

## First policy contract: QwenPI_v3

- Three RGB views: head, left wrist, right wrist, in that order.
- Raw 14D dual-ARX-X5 absolute-joint state.
- Original natural-language instruction; QwenPI_v3 injects discretized state
  through its text pathway.
- `50×14` absolute joint-position proposal.
- `arx_x5` q99 unnormalization performed by the serving layer.
- Continuous gripper opening with `0=closed`, `1=open`.
- Native deployment predicts 50 actions and executes 16 before replanning.

StarRoboHarness accepts a maximum 15-step student prefix so every execution returns
to a fresh observation/proposal boundary. Local corrections use at most five
steps, 5 cm translation, and 0.35 rad rotation per arm.

## Online loop

1. Start one episode and record the exact initial observation.
2. Request a fresh policy proposal.
3. Separately assess the last execution and the next proposal's visible intent.
4. Validate the modes implemented by the selected method profile against
   freshness, evidence, geometry, units, action space, gripper semantics, and
   request identity.
5. Execute once, record actual acknowledgements, and observe again.
6. Continue until native success, timeout, or failure. Development-only stop is
   never reported as native completion.

## Research plan

### V0: faithful policy substitution

Replace π0.5 with QwenPI_v3 while preserving the outcome/intent gate,
fresh-proposal rule, bounded corrections, and native termination. This isolates
whether the hybrid method transfers to a different student policy.

### V1: context quality

Ablate one variable at a time:

- public task semantics and completion conditions;
- evidence-backed progress memory;
- compact proposal keyframes, EEF path, and gripper events;
- before/after visual deltas and targeted crops;
- short failure-pattern retrieval without case answers;
- remaining environment, latency, and call budget.

### V2: decision quality

- Calibrate takeover and false-takeover rates.
- Improve grasp confirmation, retry, container clearance, release, retraction,
  and arm-return behavior.
- Share EEF compilation and tracing between hybrid and direct reasoner control.
- Keep GPT Direct improvements task-independent where possible.

### V3: efficiency

- Trigger strong reasoning around contact, gripper changes, stalls, and subgoal
  transitions rather than every boundary.
- Route routine checks to lower effort and difficult recovery to higher effort.
- Keep skill, robot contract, and task semantics in a stable cacheable prefix.
- Send previews by default and fetch original images/crops only when needed.
- Overlap non-mutating proposal summarization, trace writes, and next-case setup.

## Evaluation

Explicit method IDs:

- `qwenpi_v3`
- `qwenpi_v3_plus_gpt`
- `pi05`
- `pi05_plus_gpt`
- `gpt_direct`

Stages:

1. one-case contract smoke, excluded from performance claims;
2. paired development cases with identical task/layout/seed;
3. frozen held-out paired panel;
4. full 42-task RoboDojo protocol after the adapter is stable.

Report native success, native score, paired win/tie/loss, failure recovery,
false takeover, GPT calls/tokens/cost, p50/p95 decision latency, policy latency,
correction ratio, wall time, GPU-hours, and infrastructure failure separately.

Every result includes code commit, dirty state, checkpoint digest, environment,
case-manifest digest, policy/action contract, reasoner model and effort, skill
digest, context version, and artifact paths. Published reference values and
locally reproduced values remain separate.

## Milestones

- **M0 — Reproduction:** freeze manifests for GPT-as-Policy and QwenPI_v3.
- **M1 — Core:** contracts, gate, trace, fake runtime, and conformance tests.
- **M2 — Native QwenPI_v3:** prove inference/action parity with StarVLA.
- **M3 — Hybrid smoke:** run QwenPI_v3 + GPT with evidence-backed takeover.
- **M4 — Quality:** perform isolated context and recovery ablations.
- **M5 — Efficiency:** lower calls, tokens, latency, or cost at target quality.
- **M6 — Generalization:** add a non-VLA policy and a second environment without
  adding their constants to the core package.

## Collaboration boundary

The `GPT_Pai` workstream owns GPT-as-Policy/π0.5/direct reproduction. The
`QWenPI_v3` workstream owns the StarVLA checkpoint and native RoboDojo baseline.
StarRoboHarness consumes versioned manifests from both and owns common contracts,
paired evaluation, hybrid improvements, efficiency research, and contributor
experience.

The project succeeds when a new policy needs little adapter code, every
intervention has evidence, every gain survives paired evaluation, and every
gain states its latency and compute cost.
