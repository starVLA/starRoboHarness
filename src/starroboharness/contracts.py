"""Provider-, policy-, and simulator-neutral data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray


class ContractError(ValueError):
    """Raised before execution when a contract cannot be proven valid."""


@dataclass(frozen=True)
class Observation:
    """One exact post-ACK observation used to request a policy proposal."""

    observation_id: str
    instruction: str
    images: Mapping[str, Any]
    proprio: Any
    step_id: int
    remaining_steps: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.observation_id or not self.instruction:
            raise ContractError("observation_id and original instruction are required")
        if type(self.step_id) is not int or self.step_id < 0:
            raise ContractError("step_id must be a non-negative integer")
        if type(self.remaining_steps) is not int or self.remaining_steps < 0:
            raise ContractError("remaining_steps must be a non-negative integer")
        state = np.asarray(self.proprio)
        if state.ndim != 1 or not np.issubdtype(state.dtype, np.number):
            raise ContractError("proprio must be one numeric vector")
        if not np.isfinite(state).all():
            raise ContractError("proprio contains non-finite values")


@dataclass(frozen=True)
class Proposal:
    """A policy action chunk bound to one observation and one action contract."""

    proposal_id: str
    policy_id: str
    observation_id: str
    action_space: str
    actions: NDArray[np.floating]
    execute_horizon: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, *, action_dim: int | None = None) -> None:
        if not self.proposal_id or not self.policy_id or not self.observation_id:
            raise ContractError("proposal identity is incomplete")
        if not self.action_space:
            raise ContractError("action_space is required")
        actions = np.asarray(self.actions)
        if actions.ndim != 2 or actions.shape[0] < 1:
            raise ContractError("actions must have shape [horizon, action_dim]")
        if action_dim is not None and actions.shape[1] != action_dim:
            raise ContractError(f"expected action_dim={action_dim}, got {actions.shape[1]}")
        if actions.dtype.kind != "f" or not np.isfinite(actions).all():
            raise ContractError("actions must be finite floating-point values")
        if type(self.execute_horizon) is not int or not 1 <= self.execute_horizon <= len(actions):
            raise ContractError("execute_horizon must be within the proposal horizon")

    def assert_fresh(self, observation: Observation) -> None:
        if self.observation_id != observation.observation_id:
            raise ContractError("proposal is stale or belongs to another observation")
