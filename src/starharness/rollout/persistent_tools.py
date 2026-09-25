"""Vendored execution contracts with explicit starRoboHarness method identity.

Physics, gate validation, fresh proposal enforcement and bounded IK use the
attributed ``hybrid_rollout`` sources bundled with starRoboHarness.
"""

from hybrid_rollout.robodojo.robodojo_server.client import RoboDojoTools
from hybrid_rollout.robodojo.robodojo_server.gpt_only_client import GPTOnlyTools

from .controller import save_json

VARIANT = "persistent_full_agent_v1"


class IdentifiedStart:
    def __init__(self, *args, provider, **kwargs):
        self.provider = provider
        super().__init__(*args, **kwargs)

    def _rpc(self, op, **kwargs):
        if op == "record_codex_decision":
            kwargs["response"] = dict(kwargs["response"],
                                      evaluation_method=self.evaluation_method)
        return super()._rpc(op, **kwargs)

    def start(self, **arguments):
        directory = self._check("robodojo_start", arguments)
        self.sim = self.rpc_factory("127.0.0.1", self.sim_port, timeout=600)
        self.meta = self.sim.request("metadata")
        if self.meta["task"] != self.task:
            raise RuntimeError("Launched RoboDojo task differs from requested task")
        direct = self.student is None
        identity = None if direct else self.student.metadata["checkpoint_sha256"]
        version = "gpt_direct" if direct else f"QwenPI_v3/{identity[:16]}"
        self.evaluation_method = "gpt_direct" if direct else "qwenpi_v3_plus_gpt"
        reset = self.sim.request("reset", seed=self.seed, source=self.source,
                                 policy_version=version)
        if reset.get("instruction"):
            self.meta["instruction"] = reset["instruction"]
        self.episode, self.tick = reset["episode_id"], reset["step_id"]
        self.require_native_termination = bool(reset.get("metadata", {}).get("evaluation_case"))
        self._rpc(
            "begin_combination",
            teacher_model="gpt-6-astra",
            teacher_model_provider=self.provider,
            context_version=VARIANT,
            evaluation_method=self.evaluation_method,
            prompt_sha256=self.prompt_sha256,
            student_policy_version=None if direct else version,
            student_policy_sha256=identity,
            workspace_contract="starharness.agent_workspace.v2",
            category_completion_policy="ledger_and_verify_before_switch",
        )
        if direct:
            self._rpc("switch_control_source", source="gpt_eef",
                      reason="GPT Direct observation-to-action baseline")
        self.run = {
            "schema": "starharness.persistent_run.v1",
            "implementation_variant": VARIANT, "evaluation_method": self.evaluation_method,
            "teacher_model": "gpt-6-astra", "teacher_reasoning_effort": "xhigh",
            "teacher_model_provider": self.provider, "upstream_identity_verified": False,
            "teacher_prompt_sha256": self.prompt_sha256,
            "task": self.task, "instruction": self.meta["instruction"], "seed": self.seed,
            "evaluation_case": reset.get("metadata", {}).get("evaluation_case"),
            "student_backend": None if direct else self.student.metadata["backend"],
            "student_identity_sha256": identity,
            "student_server_metadata": None if direct else self.student.metadata,
            "max_episode_steps": self.meta["max_episode_steps"],
            "control_dt": self.meta["control_dt"], "max_decisions": self.max_decisions,
            "require_native_termination": self.require_native_termination,
            "initial_state_hash": reset.get("initial_state_hash"), "no_rollback": True,
            "workspace_contract": "starharness.agent_workspace.v2",
            "category_completion_policy": "ledger_and_verify_before_switch",
        }
        save_json(self.output / "run.json", self.run)
        save_json(self.output / "history.json", self.history)
        self.phase = "act" if direct else "infer"
        return self._observation(directory)


class QwenPITools(IdentifiedStart, RoboDojoTools):
    def next_call(self):
        expected = super().next_call()
        if expected and expected["tool"] == "pi05_infer":
            expected = dict(expected, tool="policy_infer")
        return expected

    def _check(self, name, arguments):
        # Upstream infer() internally checks its legacy method name. The public
        # tool name and all model-visible next_call packets are policy-neutral.
        return super()._check("policy_infer" if name == "pi05_infer" else name, arguments)


class DirectTools(IdentifiedStart, GPTOnlyTools):
    def _observation(self, directory, *, result=None):
        # Upstream act() hardcodes its legacy alias in local history.
        # Canonicalize starRoboHarness artifacts before exposing the observation;
        # native RPC identity is already set by IdentifiedStart._rpc().
        for entry in self.history:
            entry["evaluation_method"] = "gpt_direct"
            if isinstance(entry.get("response"), dict):
                entry["response"]["evaluation_method"] = "gpt_direct"
        save_json(self.output / "history.json", self.history)
        packet = super()._observation(directory, result=result)
        packet["evaluation_method"] = "gpt_direct"
        save_json(self.observation_path, packet)
        return packet

    def finish(self, reason):
        result = super().finish(reason)
        result["evaluation_method"] = "gpt_direct"
        save_json(self.output / "result.json", result)
        return result
