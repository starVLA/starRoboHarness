import json

import pytest

from starroboharness.evaluation import METHODS
from starroboharness.rollout.campaign import finish_campaign


def rows():
    return [dict(method=m, case_id="case", complete=True,
                 valid_for_success_rate=True, success=False) for m in METHODS]


def test_all_native_failures_still_complete_campaign(tmp_path):
    finish_campaign(
        tmp_path,
        {"cases": [{"case_id": "case"}], "methods": list(METHODS)},
        rows(),
        stopped=False,
    )
    assert json.loads((tmp_path / "campaign-status.json").read_text())["complete"]


@pytest.mark.parametrize("problem", ["missing", "invalid", "stopped", "duplicate"])
def test_incomplete_campaign_exits_nonzero_with_receipt(tmp_path, problem):
    outcomes = rows()
    if problem == "missing":
        outcomes.pop()
    elif problem == "invalid":
        outcomes[-1]["valid_for_success_rate"] = False
    elif problem == "duplicate":
        outcomes[-1] = outcomes[0].copy()
    with pytest.raises(SystemExit) as error:
        finish_campaign(
            tmp_path,
            {"cases": [{"case_id": "case"}], "methods": list(METHODS)},
            outcomes,
            stopped=problem == "stopped",
        )
    assert error.value.code == 2
    assert not json.loads((tmp_path / "campaign-status.json").read_text())["complete"]


def test_subset_campaign_finishes_without_unselected_direct_method(tmp_path):
    selected = ["qwenpi_v3", "qwenpi_v3_plus_gpt"]
    outcomes = [
        dict(
            method=method,
            case_id="case",
            complete=True,
            valid_for_success_rate=True,
            success=False,
        )
        for method in selected
    ]
    finish_campaign(
        tmp_path,
        {"cases": [{"case_id": "case"}], "methods": selected},
        outcomes,
        stopped=False,
    )
    assert json.loads((tmp_path / "campaign-status.json").read_text())["complete"]
