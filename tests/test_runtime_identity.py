import pytest

from starroboharness.rollout.campaign import verify_policy_runtime


class FakeCluster:
    def __init__(self, checkpoint="checkpoint-sha", patch="patch-sha"):
        self.checkpoint = checkpoint
        self.patch = patch

    def capture(self, pod, command, *, timeout=300):
        assert pod == "policy-pod"
        if command.startswith("sha256sum"):
            return f"{self.checkpoint}  /checkpoint.pt"
        if " diff " in command:
            return f"{self.patch}  -"
        if command.endswith("rev-parse HEAD"):
            return "starvla-commit"
        raise AssertionError(command)


def config():
    return {
        "policy_pod": "policy-pod",
        "checkpoint": "/checkpoint.pt",
        "checkpoint_sha256": "checkpoint-sha",
        "starvla_source": "/starvla",
        "starvla_commit": "starvla-commit",
        "starvla_normalization_patch_sha256": "patch-sha",
    }


def test_runtime_identity_checks_checkpoint_and_patch_before_reset():
    identity = verify_policy_runtime(FakeCluster(), config())
    assert identity["verified_before_reset"] is True
    assert identity["starvla_commit"] == "starvla-commit"


@pytest.mark.parametrize(
    ("cluster", "message"),
    [
        (FakeCluster(checkpoint="wrong"), "checkpoint"),
        (FakeCluster(patch="wrong"), "normalization patch"),
    ],
)
def test_runtime_identity_fails_closed_on_drift(cluster, message):
    with pytest.raises(ValueError, match=message):
        verify_policy_runtime(cluster, config())


def test_runtime_identity_rejects_different_commit_even_with_same_patch():
    frozen = config()
    frozen["starvla_commit"] = "another-commit"
    with pytest.raises(ValueError, match="StarVLA commit differs"):
        verify_policy_runtime(FakeCluster(), frozen)
