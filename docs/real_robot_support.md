# Real-robot support boundary

starRoboHarness keeps hardware drivers behind adapters. The core loop only
assumes a small interface:

- observation acquisition with a timestamp and sensor identity;
- bounded action submission through one controller;
- an immediate safety-stop path;
- monotonic step and episode identifiers;
- a native terminal receipt from the robot task evaluator.

A real-robot adapter should live outside the simulator package and provide a
contract test for reset, one action, timeout, stop, and terminal receipt. It must
record the robot model, firmware, camera layout, action space, calibration
revision, and harness commit in the run manifest.

The public repository currently documents the boundary and keeps the default
installation simulator-agnostic. No physical-robot score is claimed without a
native receipt and a declared denominator. See `docs/repository_layout.md` for
the adapter split and `CONTRIBUTING.md` for the review checklist.
