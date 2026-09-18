# Formal evaluation recovery contract

Read this reference only for multi-episode launch, recovery, or reporting.

## Preserve comparable evidence

- Treat the frozen panel digest, method profile, case ID, seed, checkpoint, and
  native RoboDojo receipt as the comparison identity.
- Reuse every hash-verified valid terminal receipt, including native failures
  and timeouts. Never rerun it merely to seek a better score.
- Do not substitute a published aggregate or a run from another panel for a
  missing paired case. It may be cited as external context, not entered into the
  formal denominator.
- Infrastructure-invalid attempts remain visible and stay outside SR and Score.

## Retry boundary

A retry is automatic only before robot control begins. A case is pre-control
when its attempt has no `controller/run.json`, `controller/progress.json`, or
`controller/history.json`. Kubernetes port-forward startup may be serialized
and retried with bounded attempts; retain an attempt receipt.

If any control acknowledgement may have occurred, do not replay the case
silently. First recover a complete native receipt or require explicit review.
Never delete or overwrite the earlier attempt.

Provider fallback is separate from simulator recovery. Switch provider only on
retained quota, rate-limit, credit, or capacity evidence and only after the
fallback provider passes the same model/effort transport preflight.

## Parallel recovery

Keep both methods for one case on the same GPU slot and run them sequentially;
skip a method that already has a verified receipt. Different cases may run in
parallel up to the verified GPU count. Use fresh output and supervisor paths.

Estimate completion from retained wall time by method and task. Sum remaining
paired work per worker, report a range that includes the slowest observed task,
and state the assumptions rather than extrapolating from control-step count.

## Dashboard evidence

Expose task-scoped camera history and public GPT decision records. A decision
should link to the nearest retained observation step. Do not label public
summaries as private hidden chain-of-thought. A missing timeline must be checked
against the full retained log before concluding that GPT did not run.
