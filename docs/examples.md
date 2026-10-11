# Examples

## Contract-only loop

The dependency-light example exercises observation, proposal, decision, bounded execution, and receipt handling:

```bash
python examples/minimal_loop.py
```

## Preflight a frozen panel

```bash
python -m starharness.rollout.local_campaign \
  --config local/runtime.json \
  --panel configs/evaluation/robodojo_1task_v1.json \
  --output artifacts/preflight-001 \
  --preflight
```

The preflight checks configuration and adapter contracts without starting an episode.

## Add an integration

Keep provider and simulator imports inside the adapter. Add a manifest under `configs/`, a launcher or audit command under `scripts/`, and tests for the public behavior. Never make the core package depend on a specific model checkpoint or cluster path.
