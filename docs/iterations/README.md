# Collaborator start here

starRoboHarness is an alpha research codebase. Read these documents in order before
changing a policy adapter, reasoner backend, or evaluation protocol:

The dated records below intentionally retain the historical `UnityPolicy`
project name and paths. They are evidence of earlier releases, not current
package identifiers; new code and public documentation use `starRoboHarness`.

1. [Dev three-case validation](2026-09-25-dev-three-case-validation.md) — the
   latest receipt-verified dev result and handoff boundary.
2. [v0.1.0-alpha.2 publication record](2026-09-18-v0.1.0-alpha.2.md) — the
   latest redacted results, usage budget, and evidence boundary.
3. [v0.1.0-alpha.1 iteration record](2026-09-17-v0.1.0-alpha.1.md) — the
   original implementation snapshot and its limitations.
4. [Architecture](../architecture.md) — stable boundaries and ownership.
5. [Evaluation protocol](../evaluation.md) — validity and comparison rules.
6. [Live evaluation](../live-evaluation.md) — public runner contract.
7. [Contributing](../../CONTRIBUTING.md) — setup, checks, adapters, and pull
   request expectations.

## Collaboration rules

- Branch from `main`; keep one contract or experiment change per pull request.
- Do not modify a frozen formal method after seeing its outcomes. Develop on
  off-panel cases, document the change, then freeze a new method identity.
- Preserve native outcomes and failed attempts. Never turn pending,
  interrupted, or infrastructure-invalid episodes into zero-success results.
- Keep the core package free of StarVLA, RoboDojo, Codex, and scheduler imports.
  Integrations belong behind adapters or in the experimental rollout layer.
- Add a versioned iteration record when a change affects method identity,
  evaluation validity, public interfaces, or reported evidence.

## Fast local verification

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
python scripts/smoke_contracts.py
```

Persistent-agent tests require the optional GPT-as-Policy source tree on
`PYTHONPATH`; the base contract suite does not. Simulator runs additionally
require the external RoboDojo, StarVLA, assets, checkpoint, and cluster setup
described by the live-evaluation documents.
