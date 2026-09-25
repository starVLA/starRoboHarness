# Public RoboDojo policy context

The host provides the original task instruction, three RGB views, measured
proprioception, student proposals, and exact post-acknowledgement observations.
Use only this visible episode evidence. Do not infer hidden object state,
reward, or a future simulator snapshot.

For category-placement tasks, translate the instruction into a ledger of
category, destination, visible instances, and verified completion. Complete one
category at a time when practical, and verify containment after release before
moving to the next category.

The public workspace is an audit aid. It does not grant a second simulator
connection or permission to change host-owned evidence.
