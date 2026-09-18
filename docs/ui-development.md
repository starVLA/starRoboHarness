# StarRoboHarness UI development guide

## Purpose and safety boundary

StarRoboHarness UI is a read-only working surface for RoboDojo evaluation runs. It
may read result JSON, public reasoning records, logs, camera frames, and videos.
It must not start or stop evaluation jobs, edit campaign outputs, acknowledge a
robot action, or reinterpret an infrastructure error as a benchmark failure.

The repository source lives in `tools/dashboard/`. The current production deployment remains
separate at:

```text
.
```

Do not edit that production directory while developing. Use port 8766 or
another non-production port, validate the repository version, and deploy only
after review.

## Architecture

```text
StarRoboHarness-compatible campaign output (read only)
        |
        v
tools/dashboard/monitor_dashboard.py
  - aggregates panel, outcomes, comparison, progress, usage, and errors
  - groups progress, public decisions, errors, and media by RoboDojo task
  - atomically writes tools/dashboard/state.json every three seconds
  - serves dashboard assets and read-only media
        |
        v
tools/dashboard/dashboard.html
  - fetches state.json every three seconds
  - keeps the selected task's metrics, camera frames, timeline, and log stable
```

There is deliberately no build tool or third-party frontend dependency yet.
The dashboard is one HTML file with CSS and JavaScript, and the collector uses
the Python standard library. Preserve this low-friction path until a requested
feature materially benefits from a framework.

## Source files

| File | Responsibility |
| --- | --- |
| `tools/dashboard/dashboard.html` | Structure, warm neutral visual system, responsive layout, and client rendering |
| `tools/dashboard/monitor_dashboard.py` | Stable read-only data contract, aggregation, media routing, and HTTP server |
| `tools/dashboard/run-dev.sh` | Development launch on an isolated port |
| `tools/dashboard/state.json` | Generated state; never commit it |

The runtime `state.json` has these top-level fields:

- `generated_at`, `root`, and `status` for campaign identity and lifecycle;
- `evidence_roots` for the active campaign and immutable source runs accepted
  during resume;
- `astra` and `simulator` for per-method coverage, success, score, and errors;
- `cost` for recorded token-based estimates, not account billing;
- `task_order` and `task_views` for per-task progress, public decisions,
  isolated errors, media, cases, and log tail;
- `policy`, `video`, and `task` as backward-compatible global-latest fields.

When changing this contract, update the collector and renderer together. New
fields should tolerate partially written episodes and remain optional until all
supported run formats provide them.

## Development workflow

From the repository root:

```bash
./tools/dashboard/run-dev.sh runs/formal-four-v17-native
```

Open:

```text
http://127.0.0.1:8766/dashboard.html
```

To use another port:

```bash
PORT=8767 ./tools/dashboard/run-dev.sh runs/campaign
```

The page reloads data automatically, but HTML/CSS/JavaScript source changes
require a browser refresh. Stop the development process with `Ctrl-C`.

Before committing:

```bash
python3 -m py_compile tools/dashboard/monitor_dashboard.py
bash -n tools/dashboard/run-dev.sh
git diff --check
```

Also start the development server against both a running campaign and a stopped
campaign, confirm `dashboard.html` and `state.json` return HTTP 200, and verify
that missing camera frames, missing outcomes, and infrastructure errors render
without breaking the page.

## Understanding the evaluation counts

The current four-task panel has five cases per task and two methods per case:

```text
4 tasks x 5 cases x 2 methods = 40 episodes
20 paired cases
```

`pending` is not a failed result. A row enters the benchmark denominator only
when `valid_for_success_rate` is true. The UI must keep total episode coverage,
paired-case coverage, policy failure, and infrastructure failure visually
distinct.

## GPT reasoning and intervention timeline

The dashboard presents retained public decision evidence as a task-scoped
timeline rather than making the user follow interleaved raw JSON. Task
selection also drives the camera and policy summary, so independent writers do
not make the page jump between episodes. The collector scans the full retained
campaign log before applying a per-task display limit; a global tail can erase
an older task when several episodes write interleaved events. Frame history is
encoded as a compact observation-step list and base media URL. The browser can
scrub, step, or play those frames, and clicking a decision seeks to its nearest
retained observation step.

A resumed campaign normally stores only accepted outcome rows in the new root;
the corresponding controller frames and decision logs remain in each row's
`source_run`. The collector resolves those roots read-only, merges and
deduplicates public decisions, and serves historical media through an indexed,
path-confined URL. This keeps accepted evidence visible without copying or
rewriting experiment artifacts.

Relevant campaign files include:

- `reasoner/public_reasoning.jsonl`: concise public model commentary;
- `reasoner/rpc_out.jsonl`: raw app-server events;
- `reasoner/tool_*_request.json` and `tool_*_result.json`: tool boundaries;
- `controller/progress.json`: steps, decisions, policy calls, and timings;
- simulator `codex_decisions/*.json`: action decision and execution receipt;
- supervisor `campaign.log`: interleaved campaign events.

Do not claim or display private hidden chain-of-thought. The intended timeline
uses public reasoning and structured evidence:

```text
step -> current subgoal -> observed evidence -> approve/override mode
     -> requested steps/target -> simulator ACK -> resulting progress
```

Separate these counters in the UI:

- persistent model sessions or turns;
- GPT decisions;
- unchanged student approvals;
- action overrides and EEF recovery decisions;
- execution ACKs and failed tool calls.

The existing `reasoner_calls` value is one persistent model turn per hybrid
episode; it is not the number of GPT decisions and should not be labeled simply
as “GPT calls”.

## Remaining UI limitations

1. Task selection is stable, but selecting one exact layout within a task is
   not yet exposed as a second-level control.
2. Cost combines the active formal run and optional retained development roots.
   Those scopes remain explicit estimates, not account billing.
3. A historical pre-control error remains visible as isolated evidence even
   after a later recovery attempt succeeds; it is intentionally not deleted.

## Production deployment

Production currently listens on port 8765 and is managed independently from
this repository. Deployment should be an explicit reviewed synchronization of
the repository files, followed by a dashboard-only service restart. Never
restart or modify the evaluation runner when deploying UI changes.

At minimum, deploy:

```text
tools/dashboard/dashboard.html
tools/dashboard/monitor_dashboard.py
```

Do not deploy or commit generated `state.json`, Python cache files, local logs,
or any experiment artifact. After deployment, verify the production page,
state endpoint, media endpoint, selected campaign root, and refresh timestamp.
