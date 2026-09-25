import pytest

from starharness.rollout.campaign import case_ports, cases_requiring_work, parallel_case_workers


def panel():
    return {
        "methods": ["qwenpi_v3", "qwenpi_v3_plus_gpt"],
        "cases": [
            {"case_id": "a0", "task": "a"},
            {"case_id": "a1", "task": "a"},
            {"case_id": "b0", "task": "b"},
        ],
    }


def test_scheduler_keeps_partially_completed_case_for_its_missing_method():
    completed = {("qwenpi_v3", "a0"), ("qwenpi_v3_plus_gpt", "a0"), ("qwenpi_v3", "a1")}

    pending = cases_requiring_work(panel(), completed)

    assert [case["case_id"] for case in pending] == ["a1", "b0"]


def test_parallelism_is_bounded_by_pending_cases_and_gpu_slots():
    assert parallel_case_workers({"parallel_case_workers": 8}, [{}, {}, {}], 2) == 3
    assert parallel_case_workers({}, [{}, {}, {}], 2) == 2
    with pytest.raises(ValueError, match="between 1 and 8"):
        parallel_case_workers({"parallel_case_workers": 9}, [{}], 1)


def test_worker_ports_can_be_isolated_across_concurrent_campaigns():
    assert case_ports({}, 2) == (19342, 6232, 29342, 26232)
    assert case_ports({"local_sim_port_base": 30340, "local_policy_port_base": 27230}, 2) == (
        19342,
        6232,
        30342,
        27232,
    )
