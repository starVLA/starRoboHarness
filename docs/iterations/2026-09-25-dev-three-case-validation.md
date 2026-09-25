# Dev three-case validation

Date: 2026-09-25  
Status: complete development validation; one layout per task

## Result

The native `openai / gpt-6-astra / xhigh` hybrid path completed three
RoboDojo development cases with receipt-verified terminal states.

| Task | Terminal | SR | Score | Control steps | Policy calls |
| --- | --- | ---: | ---: | ---: | ---: |
| Classify objects by language | timeout | 0% | 10/100 | 1100 | 146 |
| Arrange the largest number | success | 100% | 100/100 | 487 | 34 |
| Make a Kong in Mahjong | success | 100% | 100/100 | 381 | 27 |
| **Overall** | **3/3 valid** | **66.7%** | **70/100** | **1968** | **207** |

The aggregate has full paired coverage for this three-case panel. It is a dev
validation result, not a full RoboDojo benchmark estimate: each task contains
only the standard `g0/l0` layout.

## Efficiency evidence

The three terminal receipts record 30.91M input tokens, of which 29.83M were
cached, plus 72.6k output tokens. The measured input cache fraction is 96.5%.
These are runtime usage counters, not provider billing or hidden
chain-of-thought.

The classify case used all 481 recorded correction steps and reached its native
step limit with a score of 10. The two successful cases used no correction
steps. This makes classify the clearest next target for harness and prompt
analysis; the current sample does not establish that correction itself caused
the two successes.

## Recovery and validity

- Infrastructure- and provider-invalid attempts were retained as evidence and
  excluded from SR and Score.
- A receipt-verified resume index reused only valid terminal outcomes.
- A case that had entered robot control was never replayed in place; the
  recovered run used a fresh output identity.
- The final campaign exited normally with three valid native receipts.

## Reproducibility boundary

The frozen runtime used source commit `aa14b9d`. The handoff branch includes
the subsequent recovery-lineage improvement at `504e0e2`. The full test suite
reported `127 passed`.

Raw RPC streams, camera frames, native receipts, usage snapshots, failed
attempts, infrastructure identities, and account details remain in the private
evidence bundle. This public record intentionally excludes operational paths,
credentials, and account identifiers.

## Next dev iteration

1. Diagnose the classify failure from its native trajectory and public tool
   evidence before changing the method.
2. Freeze a new method identity for any cadence, prompt, or authority change.
3. Re-run a multi-layout panel and report coverage before aggregate metrics.
4. Keep provider failures and interrupted control attempts outside SR and
   Score.
