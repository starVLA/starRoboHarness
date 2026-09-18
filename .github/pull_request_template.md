## Summary

Describe the user-visible or research-facing outcome.

## Contract impact

- [ ] No contract change
- [ ] Policy adapter
- [ ] Reasoner/gate
- [ ] Environment/action compiler
- [ ] Trace/evaluation schema
- [ ] Skill/context

List any compatibility or migration requirement.

## Validation

- [ ] `ruff check .`
- [ ] `pytest -q`
- [ ] `python scripts/smoke_contracts.py`
- [ ] Relevant adapter/environment smoke

## Evaluation integrity

If this changes reported behavior, link the versioned experiment manifest and
state whether the cases were development or frozen. Confirm that no reward,
object truth, future simulator state, or case-specific answer entered the
reasoner context.
