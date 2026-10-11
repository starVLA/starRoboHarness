# Contributing to starRoboHarness

Thank you for improving starRoboHarness. Contributions may add policy adapters, reasoner transports, simulator integrations, evaluation protocols, diagnostics, dashboard features, documentation, or paper assets.

## Development setup

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest -q
python scripts/smoke_contracts.py
```

Use a focused branch and a small commit. Keep the core package independent of heavyweight model and simulator runtimes. New integrations belong behind adapters and must include a dry-run or fake-backend test.

## Pull request checklist

- Explain the contract or user-facing behavior that changed.
- State the affected simulator, policy, reasoner, or benchmark split.
- Add tests for observable invariants and failure handling.
- Record protocol version, seed, checkpoint identity, commit, denominator, and evidence path for evaluation changes.
- Keep credentials, absolute cluster paths, checkpoints, datasets, raw trajectories, and provider transcripts out of Git.
- Update the relevant documentation, `NEWS.md`, and release notes when behavior or layout changes.

## Adapter checklist

A policy adapter documents observation keys, camera order, state dimensions, preprocessing, action units, coordinate frame, normalization ownership, checkpoint compatibility, prediction horizon, gripper semantics, proposal freshness, and malformed-input behavior.

An environment adapter keeps native success, partial score, timeout, infrastructure failure, operator stop, and budget stop distinct. It exposes one authoritative control connection per episode and records actual acknowledgements.

## Experiments and paper assets

Put small machine-readable manifests and concise interpretations under `docs/experiments/`. Put LaTeX and editable figure sources under `exps/`; put release-safe copies under `assets/`. State the hypothesis before the result. Do not tune on the final panel. Do not present a smoke run as a benchmark result.

## Security and public release

Read [`docs/public_release.md`](docs/public_release.md) before contributing to the public repository. The private evidence repository and ModelScope backup may contain operational data that must never be copied into a public branch.
