# Codex CLI and paired evaluation

## Provider preflight

Run with an existing native Codex account login:

```bash
PYTHONPATH=src python scripts/probe_codex.py \
  --output artifacts/preflight \
  --image examples/robot-observation.png
```

For an explicitly configured Responses-compatible gateway, also pass
`--base-url` and `--api-key-file`. The key is passed only in the CLI child's
environment; it is not included in the command, prompt, or provenance receipt.
Never commit authentication files. Native CLI login stays on the controller
machine; the simulator and policy services need no model credentials.

`CodexCLIReasoner.infer(prompt, schema=..., images=...)` starts one bounded,
ephemeral session, pins the model and effort explicitly, and returns structured
JSON, token usage, elapsed time, and an artifact directory. It does not change
the user's global model/provider configuration. The provider uses
`--ignore-user-config`, read-only access, no web search, and disabled shell,
multi-agent, sleep, apps, plugins, and other unrelated tools. Unexpected tool
events invalidate a response. Keep the CLI invocation in its generated working
directory, separate from model weights and simulator internals.

The provider records **requested** identity. The CLI's request configuration
does not prove how a third-party gateway implements model aliases or reasoning
effort. Record the route separately and require a real text/image preflight.
The native route was available when the public gateway returned HTTP 429.

There are no provider-level retries or model fallbacks. A transport error or
timeout yields no decision. A timeout terminates only that invocation's process
group. Callers must validate request identity and the action contract before
executing a response. An uncertain simulator ACK must never be replayed.

## Bounded context

`build_context` takes allowlisted observation/proposal fields, at most three
recent action summaries, and at most 4,000 characters of public task memory.
Attach RGB separately. It excludes result/reward fields and simulator object
truth and rejects oversized context instead of truncating robot state. Public
memory should contain visible progress, uncertainty, and the next subgoal;
it is not a private reasoning transcript.

Fresh sessions avoid ever-growing raw episode history, but add CLI startup and
fixed prompt overhead. Measure wall time and actual cached-token usage; cache
hits are not guaranteed. A bounded-context ablation should be evaluated against
the persistent-session controller before claiming a performance advantage.

## Three-method report

Freeze `benchmark`, `model`, `effort`, `methods`, and explicit cases containing
`case_id`, `task`, `eval_seed`, and `layout_id`. The methods are, in order:
`qwenpi_v3`, `gpt_direct`, `qwenpi_v3_plus_gpt`. Use `validate_panel` with the
installed task registry before simulator allocation.

Each outcome receipt binds the panel digest and contains `method`, `case_id`,
`complete`, `valid_for_success_rate`, `success`, `termination`, `score`, and
`artifact`. Native score is [0, 1]; the report converts it to [0, 100]. The
reporter checks receipt consistency; it does not independently authenticate a
simulator artifact. A future native runner must create these receipts from
the native evaluation output and archive its digest.

```bash
PYTHONPATH=src python scripts/summarize_panel.py \
  --panel artifacts/panel.json --outcomes artifacts/outcomes.json \
  --output artifacts/comparison.json
```

The report contains per-task values, per-method coverage, and paired values on
the intersection of valid cases. Missing and infrastructure-aborted cases have
no success rate when the denominator is zero. Duplicate method/case outcomes
are rejected. Retain every attempt externally; never select the best retry.

## Pending integration

These components are not yet wired into a native three-method rollout runner.
Remaining work includes the StarVLA transport, proposal/execution bridge,
episode scheduling, native outcome receipts, and the selected five-task panel.
The screenshot's five tasks are RoboLab tasks (8D single-arm control). The
current checkpoint requires RoboDojo (14D dual-ARX-X5 control). Task selection
must be resolved before freezing cases; do not silently relabel RoboLab rows
as RoboDojo or pad an incompatible action vector.

Codex CLI interface reference:
[Non-interactive mode](https://developers.openai.com/codex/noninteractive).
