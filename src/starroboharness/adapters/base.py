"""Protocols implemented by external policy and environment integrations."""

from __future__ import annotations

from typing import Any, Protocol

from ..contracts import Observation, Proposal


class PolicyAdapter(Protocol):
    policy_id: str

    def propose(self, observation: Observation) -> Proposal: ...


class EnvironmentAdapter(Protocol):
    def start(self, *, task: str, seed: int, output_dir: str) -> Observation: ...

    def execute(self, *, proposal: Proposal, decision: dict[str, Any]) -> Observation: ...


class ReasonerAdapter(Protocol):
    def decide(self, context: dict[str, Any]) -> dict[str, Any]: ...
