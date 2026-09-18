# News

## ✨ 2026-09-19 · StarRoboHarness public refresh

- Reframed the project as an open execution, orchestration, and evaluation
  harness for reasoning-driven robotics rather than a QwenPI/GPT experiment
  repository.
- Renamed the maintained Python package to `starroboharness` and added a stable
  `starroboharness.core` contract surface while keeping simulator and provider
  dependencies behind adapters.
- Reorganized the public README around Observation, Proposal, Decision,
  Execution, Trace, integrations, reproducibility, and contribution paths.
- Kept frozen panel identities and dated experiment records compatible so old
  evidence remains auditable.

## 🧭 2026-09-18 · Public alpha refresh

- Added a publication-safe comparison of QwenPI_v3, QwenPI_v3 + GPT-6 Astra,
  and GPT-6 Astra Direct on one complete RoboDojo development case.
- Added transparent token-budget accounting with rounded, non-invoice usage
  estimates.
- Moved raw rollout evidence and operational audits to the private evidence
  bundle; the GitHub tree no longer carries cluster, account, path, or raw RPC
  details.
- Added a warm, read-only dashboard contract and contributor-facing release
  boundaries.

## 🚀 2026-09-17 · StarRoboHarness alpha

- Introduced model-neutral proposal, review, and bounded-execution contracts.
- Added the QwenPI_v3 adapter boundary, persistent reasoner hooks, and replay
  tests for terminal-result accounting.
