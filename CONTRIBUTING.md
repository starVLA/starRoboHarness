# Contributing

starRoboHarness welcomes policy, reasoner, environment, evaluation, and tooling
contributions. Keep the core package independent of heavyweight model and
simulator runtimes.

## Development setup

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
python scripts/smoke_contracts.py
```

Use a feature branch and keep commits focused. Do not commit credentials,
checkpoints, datasets, videos, trajectory arrays, or local environment paths
outside documented examples.

## Adapter checklist

A policy adapter must document and test:

- observation fields, camera names/order, state dimensions, and preprocessing;
- executable action space, dimensions, units, coordinate frame, and ordering;
- normalization ownership and checkpoint compatibility;
- prediction horizon versus maximum executed prefix;
- gripper semantics;
- proposal identity and freshness;
- explicit failures for malformed or unsupported inputs.

An environment adapter must keep native success, partial score, timeout,
infrastructure failure, and operator/budget stop distinct. It must expose one
authoritative control connection per episode and record actual acknowledgements.

## Experiments

Put small, machine-readable manifests and a concise interpretation in
`docs/experiments/`. State the hypothesis before the result. Record commits,
checkpoint identity, case manifest, seeds, protocol, exclusions, and artifact
locations. Do not present a smoke run as a benchmark result or compare metrics
from different protocols without an explicit caveat.

## Skills

Keep `SKILL.md` focused on decisions that change online behavior. Put detailed
robot or policy contracts in `references/` and link them from the entrypoint.
Never add benchmark answers, object truth, reward access, or case-specific
action scripts to a skill.

## Pull requests

Every pull request should explain the contract being changed, include tests for
observable invariants, and identify compatibility or evaluation impact. Run
the full local checks before requesting review.
