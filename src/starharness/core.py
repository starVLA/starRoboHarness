"""Stable, model-neutral public surface for the starRoboHarness loop.

The implementation remains split into focused modules, but integrations can
depend on this small module instead of reaching into rollout internals.
"""

from .adapters.base import EnvironmentAdapter, PolicyAdapter, ReasonerAdapter
from .contracts import ContractError, Observation, Proposal
from .gate import validate_decision, validate_direct_decision
from .trace import ChainedJsonlTrace

__all__ = [
    "ChainedJsonlTrace",
    "ContractError",
    "EnvironmentAdapter",
    "Observation",
    "PolicyAdapter",
    "Proposal",
    "ReasonerAdapter",
    "validate_decision",
    "validate_direct_decision",
]
