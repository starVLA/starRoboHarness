import pytest

pytest.importorskip("hybrid_rollout")
from starroboharness.rollout.campaign import check_simulator_startup, close_connections


def test_ready_does_not_override_broken_graphics():
    with pytest.raises(RuntimeError, match="preflight"):
        check_simulator_startup('Failed to create any GPU devices\n{"event": "ready"}')
    check_simulator_startup('normal extension startup\n{"event": "ready"}')


def test_failed_close_does_not_skip_remaining_connection():
    calls = []

    class Broken:
        def close(self):
            calls.append("broken")
            raise OSError("disconnected")

    class Healthy:
        def close(self):
            calls.append("healthy")

    errors = close_connections((Broken(), None, Healthy()))
    assert calls == ["broken", "healthy"]
    assert errors == [{"operation": "connection.close", "type": "OSError"}]
