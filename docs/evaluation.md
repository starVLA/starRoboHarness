# Evaluation protocol

## Method identity

Use explicit method IDs:

| Method | Student policy | Reasoner |
|---|---|---|
| `qwenpi_v3` | QwenPI_v3 | none |
| `qwenpi_v3_plus_gpt` | QwenPI_v3 | configured reasoner |
| `pi05` | π0.5 | none |
| `pi05_plus_gpt` | π0.5 | configured reasoner |
| `gpt_direct` | none | configured reasoner |

Authentication profile, provider route, or whether a server process exists may
not determine the method ID.

## Comparison stages

1. Contract smoke: one fixed case, excluded from performance claims.
2. Paired development panel: identical task, layout, seed, and termination for
   every method.
3. Frozen held-out panel: no prompt or skill changes after viewing outcomes.
4. Full benchmark: only after the adapter and paired protocol are stable.

The published GPT-as-Policy 10-task, 50-case panel and the published StarVLA
42-task, 2,100-episode table are different protocols and cannot be compared as
if they were one experiment.

## Required result fields

- repository commits and dirty state;
- checkpoint URI plus digest;
- container/environment identity;
- task, layout ID, evaluation seed, and case-manifest digest;
- policy adapter and action-contract version;
- reasoner model, snapshot, effort, skill digest, and context version;
- native success, native score, terminal state, and control steps;
- GPT calls, tokens, cached tokens, latency, correction ratio, and wall time;
- artifact root and trace/video digests;
- exclusion or retry reason, when applicable.

Report release values and locally reproduced values in separate columns.
Import tests, server health checks, and incomplete episodes are not successful
reproductions.
