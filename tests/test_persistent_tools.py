import json

import pytest

pytest.importorskip("hybrid_rollout.robodojo.robodojo_server.client")
from hybrid_rollout.robodojo.robodojo_server.gpt_only_client import GPTOnlyTools

from starroboharness.rollout.persistent_tools import DirectTools, QwenPITools


class RPC:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def request(self, op, **kwargs):
        self.calls.append((op, kwargs))
        if op == "metadata":
            return {"task": "build_tower", "instruction": "build", "max_episode_steps": 1050,
                    "control_dt": 0.04}
        if op == "reset":
            return {"episode_id": "episode", "step_id": 0,
                    "metadata": {"evaluation_case": {"case_id": "development"}}}
        return {}


class Student:
    metadata = {"checkpoint_sha256": "a" * 64, "backend": "StarVLA/PyTorch"}


def test_direct_history_uses_canonical_method_without_changing_actions(tmp_path, monkeypatch):
    tools = DirectTools(tmp_path, "build_tower", provider="test", rpc_factory=RPC)
    tools.history = [{"evaluation_method": "gpt_only", "executed_steps": 5,
                      "response": {"evaluation_method": "gpt_only", "mode": "eef"}}]
    tools.observation_path = tmp_path / "observation.json"
    monkeypatch.setattr(GPTOnlyTools, "_observation", lambda self, directory, result=None:
                        {"evaluation_method": "gpt_only", "history": self.history})
    packet = tools._observation(tmp_path)
    assert packet["evaluation_method"] == "gpt_direct"
    history = json.loads((tmp_path / "history.json").read_text())
    assert history[0]["evaluation_method"] == "gpt_direct"
    assert history[0]["response"] == {"evaluation_method": "gpt_direct", "mode": "eef"}
    assert history[0]["executed_steps"] == 5


@pytest.mark.parametrize("direct", [False, True])
def test_start_records_actual_method_and_never_openpi(tmp_path, direct):
    cls = DirectTools if direct else QwenPITools
    args = (tmp_path, "build_tower") if direct else (tmp_path, "build_tower", Student())
    tools = cls(*args, provider="test-provider", rpc_factory=RPC, max_decisions=0)
    tools._observation = lambda directory: {"next_call": tools.next_call()} if direct else {}
    # Direct next_call needs the observation file assigned by the real recorder.
    tools.observation_path = tmp_path / "observation.json"
    tools.start(task="build_tower", output_dir=str(tmp_path / "observations/000"))
    run = json.loads((tmp_path / "run.json").read_text())
    expected = "gpt_direct" if direct else "qwenpi_v3_plus_gpt"
    assert run["evaluation_method"] == expected
    assert run["teacher_model_provider"] == "test-provider"
    assert "OpenPI" not in json.dumps(run)
    assert run["student_backend"] == (None if direct else "StarVLA/PyTorch")
    assert tools.require_native_termination
    assert sum(op == "reset" for op, _ in tools.sim.calls) == 1
    if not direct:
        assert tools.next_call()["tool"] == "policy_infer"
        with pytest.raises(ValueError):
            tools._check("pi05_infer", {"observation_path": "stale", "output_dir": "wrong"})


def test_episode_uses_layout_reset_seed_not_eval_seed(tmp_path, monkeypatch):
    from starroboharness.rollout import persistent_episode as module

    class Worker:
        prompt_sha256 = "test"

        def __init__(self, *args, **kwargs):
            pass

        def run(self, rollout):
            assert rollout.seed == 5
            (rollout.output / "result.json").write_text('{"truncated": true}')

        def close(self):
            pass

    class Tools:
        def __init__(self, output, task, **kwargs):
            self.output, self.seed = output, kwargs["seed"]

        def close(self):
            pass

    monkeypatch.setattr(module, "PersistentAgent", Worker)
    monkeypatch.setattr(module, "DirectTools", Tools)
    result = module.run_persistent(
        root=tmp_path, method="gpt_direct",
        case={"runtime_task": "build_tower", "layout_id": 5, "eval_seed": 0},
        config={"codex": "test", "codex_provider": "test"}, connection=None,
        sim_port=1234, runtime_identity={},
    )
    assert result["truncated"]
