# VLAct support

The public release includes the contract description and a fail-closed preflight
for the released RoboDojo VLAct checkpoint. It does not bundle model weights or
provider credentials.

## RoboDojo contract

`configs/vlact_robodojo.json` records the released model's native contract:
three RGB views at 224×224, a 14D ARX X5 state, a 50×14 action chunk, `arx_x5`
unnormalization, and a 16-action execution horizon. The preflight command is:

```bash
python scripts/preflight_vlact_contract.py \
  --config configs/vlact_robodojo.json
```

The check rejects dimension or embodiment mismatches. It never pads, slices, or
silently remaps an action vector.

## Downstream embodiments

The development tree also contains separate adapters for BEHAVIOR R1Pro and
SimplerEnv WidowX/Google Robot policies. They have different state and action
spaces and must use their own model head, normalization, and native evaluator.
A RoboDojo VLAct result cannot be reported as a BEHAVIOR or SimplerEnv result.

The current development records are diagnostic and are listed here to make the
scope explicit. They are not a public leaderboard and do not include private
checkpoint paths or raw rollout logs.
