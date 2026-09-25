import json

import pytest

from starharness.contracts import ContractError
from starharness.trace import ChainedJsonlTrace


def test_trace_round_trip_and_resume(tmp_path):
    path = tmp_path / "trace.jsonl"
    trace = ChainedJsonlTrace(path)
    first = trace.append("observation", {"id": "obs-0"})
    second = trace.append("proposal", {"id": "proposal-0"})
    assert second["previous_sha256"] == first["sha256"]

    resumed = ChainedJsonlTrace(path)
    third = resumed.append("decision", {"mode": "student"})
    assert third["sequence"] == 2
    assert len(resumed.read_all()) == 3


def test_trace_detects_tampering(tmp_path):
    path = tmp_path / "trace.jsonl"
    trace = ChainedJsonlTrace(path)
    trace.append("observation", {"id": "obs-0"})
    row = json.loads(path.read_text())
    row["payload"]["id"] = "changed"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ContractError, match="digest"):
        ChainedJsonlTrace(path)
