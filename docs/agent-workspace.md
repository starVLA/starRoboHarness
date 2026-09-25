# Persistent agent workspace

Each persistent RoboDojo episode receives a fresh, auditable workspace beside
its controller artifacts. The public harness mirrors the useful upstream
contract without copying site-specific launch data:

```text
agent/
├── AGENTS.md                         # operating and evidence boundary
├── NOTES.md                          # visible episode memory
├── workspace.json                    # paths, method, and context hashes
├── context/
│   ├── teacher_context.md            # public observation rules
│   └── eef_control.md                # dual-arm control contract
├── scratch/                          # temporary crops/calculations
└── .agents/skills/robodojo-*/        # discoverable public skill + gate
```

The manifest records `baseline_full_conversation_available: false`; public
decision records are not a claim to expose private chain-of-thought. Raw RPC,
frames, trajectories, checkpoints, credentials, and cluster paths remain
outside the repository.

For category-placement tasks, injected public task context asks the model to
maintain an instance ledger. This is model guidance, not a visual-state validator
or a hard scheduling lock; the outcome/intent takeover gate remains unchanged.
A category should be marked complete only after every visible
instance is in the instructed destination and a fresh observation verifies the
release. The intended effect is to reduce spreading corrections across categories
without completing one; that performance effect requires paired evaluation.

The workspace helper is `starharness.rollout.public_workspace` and is invoked
by the persistent reasoner before the first app-server thread starts.
