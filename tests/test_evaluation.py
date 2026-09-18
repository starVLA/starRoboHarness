import copy

import pytest

from starroboharness.contracts import ContractError
from starroboharness.evaluation import METHODS, panel_digest, summarize, validate_panel


def panel():
    return {
        "benchmark": "RoboDojo",
        "methods": list(METHODS),
        "model": "gpt-6-astra",
        "effort": "xhigh",
        "cases": [{"case_id": "tower-0", "task": "build_tower", "layout_id": 0, "eval_seed": 0}],
    }


def outcome(method, *, success=True):
    return {
        "method": method,
        "case_id": "tower-0",
        "panel_sha256": panel_digest(panel()),
        "valid_for_success_rate": True,
        "complete": True,
        "success": success,
        "termination": "native_success" if success else "native_timeout",
        "score": 1.0 if success else 0.3,
        "artifact": "sim/evaluation_outcome.json",
    }


def test_missing_and_infrastructure_outcomes_are_not_zero_success():
    failed = outcome("gpt_direct")
    failed.update(valid_for_success_rate=False, complete=False, termination="api_error")
    result = summarize(panel(), [outcome("qwenpi_v3"), failed])
    assert result["methods"]["qwenpi_v3"]["success_rate"] == 1
    assert result["methods"]["gpt_direct"]["success_rate"] is None
    assert result["methods"]["qwenpi_v3_plus_gpt"]["coverage"] == 0
    assert result["paired_coverage"] == 0
    assert result["paired_methods"]["qwenpi_v3"]["success_rate"] is None


def test_only_same_frozen_cases_can_form_a_comparison():
    rows = [outcome(m, success=m != "qwenpi_v3") for m in METHODS]
    result = summarize(panel(), rows)
    assert result["complete"] is True
    assert result["methods"]["qwenpi_v3"]["score"] == 30
    with pytest.raises(ContractError, match="duplicate"):
        summarize(panel(), rows + [rows[0]])
    changed = copy.deepcopy(rows)
    changed[0]["panel_sha256"] = "other-panel"
    with pytest.raises(ContractError, match="different frozen panel"):
        summarize(panel(), changed)


def test_reject_benchmark_mismatch_and_false_terminal_success():
    wrong = panel()
    wrong["benchmark"] = "RoboLab"
    with pytest.raises(ContractError, match="dual ARX"):
        validate_panel(wrong)
    with pytest.raises(ContractError, match="not a registered"):
        validate_panel(panel(), available_tasks={"BlocksInBinTask"})
    row = outcome("qwenpi_v3")
    row["termination"] = "controller_error"
    with pytest.raises(ContractError, match="native termination"):
        summarize(panel(), [row])


def test_distinct_runtime_variants_can_share_layout_number():
    data = panel()
    data["cases"] = [
        {
            "case_id": variant,
            "task": "pack_objects_into_box",
            "runtime_task": variant,
            "layout_id": 0,
            "eval_seed": 0,
        }
        for variant in ("pack_objects_into_box", "pack_objects_into_box_random")
    ]
    validate_panel(data)
    data["cases"][1]["runtime_task"] = data["cases"][0]["runtime_task"]
    with pytest.raises(ContractError, match="duplicate"):
        validate_panel(data)


def test_efficiency_distinguishes_missing_counters_and_real_zero_calls():
    row = outcome("qwenpi_v3")
    assert summarize(panel(), [row])["methods"]["qwenpi_v3"]["efficiency"] == {
        "episodes_with_metrics": 0
    }
    row["metrics"] = {"reasoner_calls": 0, "control_steps": 16, "correction_steps": 0}
    eff = summarize(panel(), [row])["methods"]["qwenpi_v3"]["efficiency"]
    assert eff["episodes_with_metrics"] == 1
    assert eff["seconds_per_reasoner_call"] is None
    assert eff["correction_fraction"] == 0
    assert eff["input_cache_fraction"] is None


def test_invalid_attempt_cost_is_visible_without_affecting_success_rate():
    row = outcome("gpt_direct")
    row.update(valid_for_success_rate=False, complete=False, termination="infrastructure_error",
               metrics={"usage": {"input_tokens": 293028}, "reasoner_calls": 1,
                        "reasoner_call_unit": "persistent_model_turn"})
    report = summarize(panel(), [row])["methods"]["gpt_direct"]
    assert report["valid"] == 0
    assert report["efficiency"]["episodes_with_metrics"] == 0
    assert report["all_attempts_efficiency"]["tokens"]["input_tokens"] == 293028


def test_call_units_are_not_averaged_together():
    from starroboharness.evaluation import efficiency_summary

    report = efficiency_summary([
        {"metrics": {"reasoner_calls": 10, "reasoner_seconds": 100}},
        {"metrics": {"reasoner_calls": 1, "reasoner_seconds": 200,
                     "reasoner_call_unit": "persistent_model_turn"}},
    ])
    assert report["seconds_per_reasoner_call"] is None
    assert report["reasoner_calls_by_unit"] == {
        "ephemeral_inference": 10, "persistent_model_turn": 1}


def test_panel_can_select_a_paired_subset_without_waiting_for_direct():
    data = panel()
    data["methods"] = ["qwenpi_v3", "qwenpi_v3_plus_gpt"]
    rows = []
    for method in data["methods"]:
        row = outcome(method, success=method == "qwenpi_v3_plus_gpt")
        row["panel_sha256"] = panel_digest(data)
        rows.append(row)
    report = summarize(data, rows)
    assert report["complete"] is True
    assert set(report["methods"]) == set(data["methods"])
    assert "gpt_direct" not in report["methods"]


@pytest.mark.parametrize(
    "methods",
    [[], ["qwenpi_v3", "qwenpi_v3"], ["qwenpi_v3", "unknown"]],
)
def test_panel_rejects_empty_duplicate_or_unknown_method_sets(methods):
    data = panel()
    data["methods"] = methods
    with pytest.raises(ContractError, match="nonempty unique subset"):
        validate_panel(data)
