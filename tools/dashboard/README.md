# RoboDojo live dashboard

This directory contains the source of the StarRoboHarness RoboDojo monitor.

## Files

- `dashboard.html`: responsive task-scoped UI, styles, and rendering logic.
- `monitor_dashboard.py`: read-only campaign collector and HTTP/media server.
- `run-dev.sh`: isolated local development launcher; defaults to port 8766.
- `state.json`: generated runtime state, intentionally ignored by Git.

## Quick start

```bash
./run-dev.sh runs/formal-four-v17-native
```

Override the development port when needed:

```bash
PORT=8767 ./run-dev.sh runs/campaign
```

The collector reads the campaign tree, atomically refreshes `state.json`, and
serves both static UI files and read-only media. It never launches, stops, or
edits an evaluation.

Each RoboDojo task has a stable entry. Selecting it pins camera frames, policy
progress, isolated infrastructure evidence, and the public GPT decision
timeline to that task; the browser remembers the selection instead of jumping
to whichever episode updated most recently. The timeline contains retained
public decision evidence, not private hidden chain-of-thought. Historical RGB
frames can be scrubbed, stepped, or played; clicking a GPT decision seeks to
the nearest retained observation step. When a campaign resumes from an older
run, accepted rows keep their original `source_run`; the monitor follows those
read-only evidence roots so historical frames and decisions do not disappear.
