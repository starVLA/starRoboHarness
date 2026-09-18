import pytest

from starroboharness.rollout.campaign import validate_reasoner_backend


@pytest.mark.parametrize("backend", ["persistent_full_agent_v1", "compact"])
def test_explicit_backend_accepted(backend):
    validate_reasoner_backend({"reasoner_backend": backend})


@pytest.mark.parametrize("config", [{}, {"reasoner_backend": None},
                                    {"reasoner_backend": "persistent_full_agent_v2"}])
def test_missing_or_unknown_backend_rejected(config):
    with pytest.raises(ValueError, match="reasoner_backend must explicitly"):
        validate_reasoner_backend(config)
