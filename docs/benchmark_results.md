# Benchmark results and update index

This page is the public index for benchmark status. It separates a reproducible
contract check from a native score and records where the detailed evidence lives.
The public repository contains reviewed summaries and figures; raw trajectories,
private dashboards, checkpoints, and cluster paths stay outside the release.

## RoboDojo

The README figure is the matched policy/hybrid development comparison used by the
technical report. `assets/figures/robodojo-results.svg` is its editable source.
The archived 50-case scene index is reproduced from Table 12 of the paper in
`assets/figures/robodojo-scene-index.png`. The paper remains the authority for the
panel identity, denominator, seed, timeout rule, and exclusions.

A partial score is not a completion. Native terminal receipts define success, and
smoke runs are not added to the denominator.

## Additional benchmark contracts

| Benchmark | Public status | What is checked | What is not claimed |
| --- | --- | --- | --- |
| RoboDojo | Supported | Native receipt, task identity, action shape, and evaluation panel | A score outside the named panel |
| VLAct RoboDojo | Contract adapter included | ARX X5, 14D state/action, three RGB views, chunk shape, and normalization key | A transfer score on another embodiment |
| RoboTwin 2.0 | Development integration | Environment and action-contract preflight | Full benchmark ranking from a partial queue |
| LIBERO-Pro | Development integration | Suite discovery, reset, and native-step smoke checks | A complete multi-suite success rate |
| RoboCasa 365 | Development integration | Registration and reset smoke checks | The official 365-task score without the official target split and checkpoint |
| BEHAVIOR / SimplerEnv | Separate VLAct contracts | Embodiment-specific adapter and receipt path | Reinterpreting a 14D RoboDojo action as another action space |

The machine-readable manifest at
`configs/evaluation/additional_benchmarks_v1.json` is intentionally small and
contains no machine-specific paths. Use it as a contract checklist before adding
a private runtime configuration.

## Reporting rules

Every result update should state the benchmark split, task count, seed, horizon,
checkpoint identity, harness commit, native receipt status, and exclusions. Keep
three categories separate:

1. **Contract check**: imports, shape checks, or simulator reset.
2. **Diagnostic run**: a bounded or partial run used to find integration issues.
3. **Benchmark result**: a complete native evaluator protocol with a declared denominator.

Only the third category belongs in a leaderboard. Update this page and `NEWS.md`
when a new benchmark contract or a reviewed result becomes public.
