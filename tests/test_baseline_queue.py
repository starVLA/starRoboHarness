import json

import pytest

from starharness.rollout.baseline_queue import SameNodeCluster, accept_native, control_started


def fixture_case():
    return dict(
        case_id="pack__random__g0__l0",
        task="pack",
        runtime_task="pack_random",
        variant="random",
        eval_seed=0,
        layout_id=0,
        reset_seed=0,
        simulator_initial_seed=0,
        policy_rng_seed=0,
        layout={"sha256": "abc"},
    )


def native(case):
    identity = {key: value for key, value in case.items() if key != "layout"}
    identity["layout_sha256"] = case["layout"]["sha256"]
    return dict(
        complete=True,
        valid_for_success_rate=True,
        evaluation_case=identity,
        native_score=0.4,
        native_success=False,
        native_control_steps=1100,
    )


def test_acceptance_requires_exact_variant_and_layout_hash(tmp_path):
    case = fixture_case()
    receipt = native(case)
    path = tmp_path / "native-outcome.json"
    path.write_text(json.dumps(receipt))
    assert accept_native(tmp_path, case)["score"] == 0.4
    receipt["evaluation_case"]["variant"] = "standard"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="identity differs"):
        accept_native(tmp_path, case)


def test_infrastructure_error_never_becomes_zero_score(tmp_path):
    receipt = native(fixture_case())
    receipt["valid_for_success_rate"] = False
    (tmp_path / "native-outcome.json").write_text(json.dumps(receipt))
    assert accept_native(tmp_path, fixture_case()) is None
    assert control_started(tmp_path)  # Native steps block replay even if marker was lost.


def test_partial_marker_and_controller_artifacts_block_retry(tmp_path):
    assert not control_started(tmp_path)
    marker = tmp_path / "control-started.json"
    marker.write_text("{")
    assert control_started(tmp_path)
    marker.unlink()
    controller = tmp_path / "controller"
    controller.mkdir()
    (controller / "run.json").write_text("{}")
    assert control_started(tmp_path)


def test_same_node_transport_rejects_tunnel_port_mismatch(tmp_path):
    cluster = SameNodeCluster(
        {"context": "unused", "namespace": "unused", "sim_pod": "node", "policy_pod": "node"}
    )
    assert cluster.command("node", "true") == ["bash", "-c", "true"]
    with pytest.raises(ValueError, match="identical"):
        cluster.forward("node", 1234, 1235, tmp_path / "forward.log")
