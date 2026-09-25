# starRoboHarness

An open execution and evaluation harness connecting robot policies, multimodal reasoners, and environments.

`Observation → Policy proposal → Decision → Guarded execution → Trace`

The core is model-neutral. QwenPI_v3, a Codex reasoner, and RoboDojo are reference integrations. Weights and simulator installations remain external; live integrations are experimental.

## Quick start

```bash
git clone https://github.com/starVLA/starRoboHarness.git
cd starRoboHarness
bash scripts/bootstrap.sh
```

This installs the lightweight harness and runs a credential-free contract smoke test. It does not install RoboDojo/Isaac or download weights.

For real evaluations, configure your separate policy and simulator runtimes using [deployment](docs/deployment.md). Run preflight before launching a frozen panel:

```bash
.venv/bin/python -m starharness.rollout.local_campaign \
  --config local/runtime.json --panel configs/evaluation/robodojo_1task_v1.json \
  --output artifacts/preflight-001 --preflight
```

## Replaceable components

| Component | Responsibility |
| --- | --- |
| `src/starharness/adapters` | Policy proposal contracts |
| `src/starharness/reasoners` | Reasoner transport |
| `src/starharness/rollout` | Service lifecycle, execution, receipts and recovery |
| `skills` | Bounded robot tools and context |
| `UI` | Read-only monitoring |

Python imports remain `starharness` for compatibility; the project and distribution are **starRoboHarness**.

## Collaborate

Contributions are welcome. See [contributing](CONTRIBUTING.md), [roadmap](docs/roadmap.md), [architecture](docs/architecture.md), and [evaluation](docs/evaluation.md).

Only complete native receipts contribute to SR/Score; infrastructure failures stay separate. Never silently replay a case after control may have started. The [paired results](docs/iterations/2026-09-25-paired-baseline.md) include regressions and do not establish universal hybrid superiority.

MIT; see [third-party notices](THIRD_PARTY_NOTICES.md).
