# Efficiency Research Handbook

This document is the working research notebook for making reasoning-policy
systems faster, cheaper, and practical without weakening evaluation fidelity or
robot safety. It is intentionally a roadmap rather than a claim that the
proposed methods already work.

starRoboHarness's first priority is a correct and reproducible three-method
evaluation. Efficiency research starts only after the activation gate below is
satisfied.

## Research thesis

A slow general reasoner should not behave like a high-frequency motor
controller. It should provide low-frequency task understanding, constraints,
exception handling, and reusable skills while a learned policy supplies
continuous closed-loop control.

The central question is:

> How can delayed System-2 reasoning be converted into safe, reusable policy
> capability with measurable gains in success, wall time, and token efficiency?

The intended outcome is a provider- and policy-neutral **latency-aware
co-control runtime**, not a collection of benchmark-specific shortcuts.

## Activation gate

Do not tune prompts, call frequency, context compression, asynchronous control,
or skill caching on the frozen performance panel until all of the following are
true:

1. `qwenpi_v3`, `qwenpi_v3_plus_gpt`, and `gpt_direct` each complete a native
   off-panel smoke episode and produce a valid terminal receipt.
2. The paired five-task development panel completes without unexplained runner
   termination, result loss, or method-dependent scene/seed drift.
3. Native success, partial score, timeout, infrastructure failure, and censored
   episodes are reported separately.
4. Resume behavior is tested for both pre-control interruption and interruption
   after the first physical ACK.
5. Observation, proposal, decision, and actual execution identities remain
   traceable end to end.
6. The reasoner and policy implementations being compared are described
   precisely enough to reproduce; compact reviewers must not be presented as
   equivalent to persistent full-agent variants.

Until this gate passes, findings in this document are diagnostic observations,
not benchmark results.

## Initial observation (2026-09-17, preliminary)

One valid `qwenpi_v3_plus_gpt` episode on
`put_bottles_into_dustbin` reached the native 700-step timeout:

| Measurement | Observed value |
|---|---:|
| Native score / success | 40 / false |
| Physical control time (`700 * 0.04 s`) | 28 s |
| End-to-end wall time | 3,091 s (51.5 min) |
| Reasoner calls | 55 |
| Cumulative reasoner time | 2,134 s (35.6 min) |
| Mean reasoner latency | 38.8 s/call |
| Policy inference time | 129 s |
| Input tokens | 916,978 |
| Cached input tokens | 402,560 |
| Uncached input tokens | 514,418 |
| Output tokens | 53,810 |

This is one episode from an interrupted development campaign. It does not
estimate success rate or stable mean efficiency. It does demonstrate that
physical duration and end-to-end duration are different quantities: the
simulator can be paused for far longer than the robot is physically controlled.

The upstream GPT-as-Policy report also presents physical duration separately
from model-response latency and describes latency as an unresolved limitation.
Its selected runs and starRoboHarness's current compact reviewer use different
implementations, contexts, and evaluation histories; their token totals must
not be treated as an apples-to-apples efficiency comparison.

## Required efficiency accounting

Every experiment must report quality, latency, and usage together. A faster run
is not an improvement if it silently changes the task, termination semantics,
action authority, or valid-result accounting.

### Quality and validity

- native success rate and native score;
- valid, incomplete, censored, retried, and infrastructure-failed episodes;
- task, layout, seed, checkpoint, method, reasoner, skill, and context identity;
- policy, reasoner correction, recovery, and rejected-action fractions.

### Time

- physical control time: `control_steps * control_dt`;
- end-to-end episode wall time;
- simulator-paused time and pause fraction;
- reasoner time, policy time, environment/reset time, and transport time;
- time to first safe action and time to recovery after a detected failure;
- reasoner latency distribution, not only the mean.

### Usage

- reasoner calls and action segments;
- input, cached input, cache-write, reasoning output, and visible output tokens;
- tokens and reasoner seconds per valid episode and per success;
- cache hit fraction and prompt/context bytes;
- provider monetary cost only when a documented price and billing boundary are
  available. Recorded tokens are not automatically a monetary bill.

### Asynchronous correctness

- observation age when a decision is received;
- stale-decision rejection and rebase rates;
- safe-prefix length executed while reasoning is in flight;
- interventions that arrive too late to affect the episode;
- safety-guard rejection and emergency-stop counts.

Report Pareto fronts over success/score, wall time, and usage. Do not collapse
them into a single unreviewed efficiency score.

## Research tracks

### R1. Event-triggered reasoning

Replace fixed frequent review with an `InterventionGate` that requests general
reasoning only when evidence indicates it may be useful. Candidate signals
include policy uncertainty, lack of object progress, failed contact or grasp,
subgoal deviation, unexpected non-termination, and disagreement between a
lightweight monitor and the active plan.

Key questions:

- Can calls fall by 5-10x without reducing native success or score?
- Which signals generalize across policies and environments?
- How should uncertainty be calibrated without granting unbounded takeover?

### R2. Pre-planning and temporal abstraction

Ask the reasoner for a task plan, subgoal graph, constraints, and recovery
branches before physical execution. Let the policy execute longer semantic
skills instead of asking the reasoner to construct short low-level segments.

The plan must remain advice, not unaudited executable code. Every concrete
action still passes through the proposal identity and safety contracts.

### R3. Asynchronous shadow reasoning

Run the reasoner concurrently while the policy executes a bounded safe prefix.
Start with `async_shadow`, where decisions are recorded but cannot control the
robot. Promote to `async_commit` only after offline replay establishes freshness
and guard behavior.

Every asynchronous response must carry the observation and proposal versions
on which it was based. The runtime must reject, revalidate, or explicitly rebase
a response when the world has advanced; it must never assume that a delayed
action remains safe.

### R4. Deliberation-to-skill compilation

Convert successful reasoning into reviewed, versioned artifacts such as
subgoal graphs, object-selection rules, recovery skills, policy-conditioning
templates, and termination checks. Retrieve a compatible skill on later
episodes and call the general reasoner only when the skill no longer applies.

The skill registry must record provenance, environment/policy compatibility,
evaluation evidence, and invalidation rules. Held-out evaluation must prevent
test-outcome leakage into a skill.

### R5. Context and cache efficiency

Investigate stable prompt prefixes, observation deltas, image deduplication,
structured state summaries, bounded rolling memory, and explicit skill
retrieval. Measure cached and uncached input separately. Reducing total token
count while increasing expensive uncached input or output is not necessarily an
improvement.

Context optimization must preserve the evidence needed to judge the previous
execution and the next proposal. Never remove evidence solely to improve a
token chart.

### R6. Adaptive reasoner budgets

Match effort, context, and tool access to decision risk. Routine progress checks
may use a small bounded reviewer; novel planning or recovery may justify a full
agent and higher reasoning effort. Compare fixed and adaptive budgets using the
same decision opportunities so that reduced capability is visible.

### R7. Parallel and speculative reasoning

Explore prefetching likely recovery branches or evaluating candidate policy
chunks concurrently. Speculation is useful only when wasted calls, stale
results, and selection bias are fully accounted for. It must not create hidden
extra inference unavailable to comparison methods.

## Proposed runtime components

These are prospective interfaces, not commitments to the current public API:

- `InterventionGate`: decides whether and why to invoke a reasoner;
- `TaskPlanner`: produces bounded subgoals and constraints;
- `AsyncReasoner`: manages in-flight requests and observation versions;
- `DecisionRebaser`: validates delayed advice against fresh state;
- `SkillRegistry`: stores versioned, evidence-backed reusable skills;
- `ActionArbiter`: selects policy, reasoner correction, or recovery authority;
- `SafetyShield`: enforces robot- and environment-specific limits;
- `EfficiencyProfiler`: emits common latency, usage, pause, and freshness data.

The core package must continue to avoid imports from a particular model
provider, robot policy, simulator, or scheduler.

## Standard experiment ladder

Run each stage on off-panel development cases first, then freeze the method
before using held-out cases.

| Stage | Method | Purpose |
|---|---|---|
| E0 | `policy_only` | learned-policy quality and latency baseline |
| E1 | synchronous review | fidelity/reference implementation |
| E2 | lower fixed review frequency | call-frequency ablation |
| E3 | event-triggered review | adaptive intervention test |
| E4 | pre-plan + policy | value of online reasoning ablation |
| E5 | asynchronous shadow | measure staleness without control risk |
| E6 | guarded asynchronous commit | latency hiding with safety checks |
| E7 | compiled skill + policy | cross-episode reuse and amortization |
| E8 | `reasoner_only` | direct-reasoner control baseline |

For each stage, retain paired tasks, layouts, seeds, native step budgets, and
termination logic. Record rejected hypotheses as well as successful ones.

## Milestones

The following targets are research hypotheses, not promised results:

1. **Instrument:** trustworthy per-component latency and token accounting.
2. **Reduce calls:** 2x fewer reasoner calls at non-inferior paired quality.
3. **Trigger:** 5x fewer calls through evidence-based intervention.
4. **Hide latency:** demonstrate safe asynchronous shadow operation and quantify
   the fraction of reasoning latency that can actually overlap execution.
5. **Reuse:** show that a compiled skill reduces repeated-episode calls and
   uncached tokens without held-out leakage.
6. **Generalize:** reproduce gains with at least two policy backends and two
   reasoner backends before claiming a starRoboHarness-level result.

Because a reasoner response can be longer than an entire physical episode,
near-real-time execution may require pre-planning, reuse, or a fast local
monitor rather than merely optimizing synchronous RPC latency.

## Experiment record template

Each research change should add a versioned record containing:

```text
Experiment ID:
Question and falsifiable hypothesis:
Code/config/skill commits:
Development or held-out status:
Tasks, cases, and manifest digest:
Methods and changed variable:
Validity/exclusion accounting:
Quality results:
Latency and pause results:
Token/cache/cost results:
Freshness and safety results:
Failure analysis:
Decision: retain, revise, or reject:
Artifacts and trace digests:
```

## Community contribution principles

- Add new gates, planners, backends, and skills behind small documented
  interfaces.
- Include a policy-free unit test and an offline replay test where applicable.
- Provide a paired ablation rather than a best-case demonstration.
- Preserve native outcomes and raw traces; do not relabel partial score as
  success.
- State which values are measured, estimated, or inferred.
- Document failure cases and added compute, including speculative calls.
- Keep provider credentials, private endpoints, and raw reasoning text out of
  public artifacts.

This handbook should evolve with evidence. Completed studies belong in
versioned experiment reports; stable conclusions should graduate into the
architecture and evaluation documentation.
