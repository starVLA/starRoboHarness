"""CVM controller: Codex owns decisions; native RoboDojo owns physics/outcomes."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

import numpy as np

from ..context import CONTEXT_VERSION, build_context, compact_eef_trajectory
from ..contracts import ContractError, Observation
from ..gate import validate_decision, validate_direct_decision
from ..trace import ChainedJsonlTrace
from .schema import decision_schema

CAMERAS = ("cam_high", "cam_left_wrist", "cam_right_wrist")
IMPLEMENTATION_VARIANT = "compact_ephemeral_reviewer_v2"
HYBRID_METHOD_PROFILE = {
    "schema": "starroboharness.method_profile.v1",
    "implementation_variant": IMPLEMENTATION_VARIANT,
    "reasoner_session": "ephemeral_per_decision",
    "reasoner_tools": [],
    "context_version": CONTEXT_VERSION,
    "current_cameras": list(CAMERAS),
    "previous_cameras": list(CAMERAS),
    "student_trajectory": "all_waypoints_compact_rows",
    "correction_modes": ["eef"],
    "gpt_as_policy_full_agent_equivalent": False,
}


def method_profile(method, baseline_action_steps=16):
    if method == "qwenpi_v3":
        return {
            "schema": "starroboharness.method_profile.v1",
            "implementation_variant": "native_qwenpi_v3_v1" if baseline_action_steps == 16
            else "development_qwenpi_v3_chunk15_ablation_v1",
            "baseline_action_steps": baseline_action_steps,
            "reasoner_session": "none",
            "reasoner_tools": [],
            "context_version": None,
            "current_cameras": list(CAMERAS),
            "previous_cameras": [],
            "student_trajectory": "not_exposed_to_reasoner",
            "correction_modes": [],
            "gpt_as_policy_full_agent_equivalent": False,
        }
    profile = dict(HYBRID_METHOD_PROFILE)
    if method == "gpt_direct":
        profile.update(
            implementation_variant="compact_ephemeral_direct_v2",
            student_trajectory="none",
        )
    return profile
PROMPT = """You are the robot policy for one live RoboDojo episode.
Choose exactly one action from the current RGB observations and measured robot state.
Return the requested JSON only, with a concise visible-evidence reason and public task
memory (at most 4000 characters). Do not use tools or assume access to hidden state.
The attached images are labeled by camera_order in the context. After the first
decision, all three previous camera views follow the three current views so you can
compare the exact before/after execution evidence.

Robot: dual ARX X5. Both arms share environment-origin XYZ coordinates in meters.
current_eef is measured link6 pose, NOT finger contact center. Quaternion is unit
wxyz. Each arm has six joints followed by gripper opening: 0 closed, 1 open.
The gripper opening is a command, NOT proof of grasp. Verify grasp and release in RGB.
An EEF target must include BOTH arms. Each target differs from current measured pose
by at most 0.05 meters and 0.35 radians. Select 1-5 control steps (25 Hz) toward it.
The host recomputes bounded robot-only IK after each step. A commanded target is
not proof of arrival. Hold the unused arm at its measured pose and intended gripper.
Follow the original instruction. Use small consistent corrections, inspect actual
motion, and keep public memory of object identities, observed progress, and the
current subgoal. Clear container rims before moving laterally. Close only when the
fingers surround the object, lift to verify the grasp, align above the destination,
lower/release, and retract. Reason about gripper geometry from images, not assumed
offsets from a different robot. After object placement, BOTH arms must return near
their initial EEF positions and orientations; reserve time for this requirement.
The host runs until native success/failure/timeout. Do not invent success or stop.
"""
HYBRID = """
You review a fresh QwenPI_v3 50-step joint proposal and its robot-only FK trajectory.
The proposal is not a simulated future scene. Separately assess the last execution
and the next proposal's intent. Use mode=student to execute 1-15 unchanged steps.
Take over with mode=eef (1-5 steps) ONLY if visible execution failed or the next
proposal clearly pursues the wrong subgoal. Uncertainty alone is insufficient.
Set target=null in student mode. Hand back as soon as a fresh proposal is aligned.
At step 0 execution_status must be not_started; never use not_started afterwards.
"""
DIRECT = "\nNo learned policy is available. Use EEF only.\n"


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


class StarVLAConnection:
    """Existing StarVLA wire format, without its global proxy-environment edits."""

    def __init__(self, port, output):
        import websockets.sync.client
        from deployment.model_server.tools import msgpack_numpy

        self.codec = msgpack_numpy
        self.output = Path(output)
        self.output.mkdir()
        self.index = 0
        self.socket = websockets.sync.client.connect(
            f"ws://127.0.0.1:{port}",
            proxy=None,
            compression=None,
            max_size=None,
            open_timeout=30,
            ping_interval=None,
        )
        self.metadata = self.codec.unpackb(self.socket.recv(timeout=30))

    def infer(self, payload):
        self.socket.send(self.codec.Packer().pack(payload))
        response = self.socket.recv(timeout=300)
        if isinstance(response, str):
            raise ContractError("StarVLA server returned an error; inspect its private log")
        decoded = self.codec.unpackb(response)
        if decoded.get("ok") and "actions" in decoded.get("data", {}):
            np.savez_compressed(
                self.output / f"raw_{self.index:05d}.npz", actions=decoded["data"]["actions"]
            )
            self.index += 1
        return decoded

    def close(self):
        self.socket.close()


class Controller:
    def __init__(self, *, sim, method, case, output, policy=None, reasoner=None, smoke_decisions=0,
                 baseline_action_steps=16):
        if baseline_action_steps not in (15, 16):
            raise ValueError("baseline_action_steps must be 15 or 16")
        self.baseline_action_steps = baseline_action_steps
        self.sim, self.method, self.case = sim, method, case
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.policy, self.reasoner = policy, reasoner
        self.smoke_decisions = smoke_decisions
        self.trace = ChainedJsonlTrace(self.output / "trace.jsonl")
        self.episode, self.step = None, 0
        self.history, self.memory = [], ""
        self.usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        self.calls = self.correction_steps = self.policy_calls = self.control_steps = 0
        self.reasoner_seconds = self.policy_seconds = 0.0
        self.previous_images = None
        self.previous_execution = None
        self.source = "student"
        self.method_profile = method_profile(method, baseline_action_steps)

    def rpc(self, op, **kwargs):
        return self.sim.request(op, episode_id=self.episode, step_id=self.step, **kwargs)

    def observe(self):
        obs = self.rpc("teacher_observation")
        folder = self.output / f"obs_{self.step:06d}"
        folder.mkdir()
        from PIL import Image

        images = []
        for camera in CAMERAS:
            path = folder / f"{camera}.png"
            Image.fromarray(obs[camera]).save(path)
            images.append(path)
        eef = {
            arm: {
                "position": obs["eef_positions"][i].tolist(),
                "quaternion_wxyz": obs["eef_quaternions_wxyz"][i].tolist(),
                "gripper_opening_command": float(obs["states"][7 * i + 6]),
            }
            for i, arm in enumerate(("left", "right"))
        }
        return obs, images, eef

    def propose(self, obs):
        import cv2

        observation = Observation(
            observation_id=f"{self.episode}:{self.step}",
            instruction=obs["instruction"],
            images={
                key: cv2.resize(obs[key], (224, 224), interpolation=cv2.INTER_AREA)
                for key in CAMERAS
            },
            proprio=obs["states"],
            step_id=self.step,
            remaining_steps=obs["remaining_steps"],
        )
        start = time.monotonic()
        proposal = self.policy.propose(observation)
        self.policy_seconds += time.monotonic() - start
        self.policy_calls += 1
        self.trace.append(
            "proposal_metadata",
            dict(
                proposal.metadata,
                proposal_id=proposal.proposal_id,
                observation_id=proposal.observation_id,
            ),
        )
        np.savez_compressed(
            self.output / f"proposal_{len(self.history):05d}.npz", actions=proposal.actions
        )
        return proposal

    def reason(self, request, images, hybrid):
        context = build_context(request, memory=self.memory, recent_actions=self.history)
        extra = {
            "camera_order": list(CAMERAS),
            "initial_eef": self.initial_eef,
            "task_context": self.task_context,
            "method_profile": self.method_profile,
        }
        image_paths = list(images)
        if self.previous_images:
            image_paths.extend(self.previous_images)
            extra["camera_order"].extend(f"previous_{camera}" for camera in CAMERAS)
        prompt = PROMPT + (HYBRID if hybrid else DIRECT)
        prompt += "\n" + json.dumps(extra) + "\n" + context
        # Rejections are pre-execution schema/bounds errors, not episode retries.
        for attempt in range(3):
            result = self.reasoner.infer(prompt, schema=decision_schema(hybrid), images=image_paths)
            self.calls += 1
            self.reasoner_seconds += result["metadata"]["wall_seconds"]
            for key in self.usage:
                self.usage[key] += result["metadata"].get("usage", {}).get(key, 0)
            decision = result["response"]
            try:
                if not isinstance(decision.get("memory"), str) or len(decision["memory"]) > 4000:
                    raise ContractError("memory must be a string of at most 4000 characters")
                if hybrid:
                    validate_decision(
                        decision,
                        request_id=request["request_id"],
                        step_id=self.step,
                        current_eef=request["current_eef"],
                    )
                else:
                    validate_direct_decision(
                        decision,
                        request_id=request["request_id"],
                        current_eef=request["current_eef"],
                    )
                self.memory = decision.pop("memory")
                self.trace.append(
                    "reasoner_decision",
                    {"decision": decision, "call_dir": result["call_dir"], "memory": self.memory},
                )
                return decision
            except (ContractError, KeyError, TypeError, AttributeError) as error:
                self.trace.append(
                    "validation_rejected",
                    {"error": str(error), "decision": decision, "physical_steps": 0},
                )
                if attempt == 2:
                    raise
                prompt += "\nYour previous JSON was rejected before execution: " + str(error)
                prompt += "\nCorrect it against the SAME unchanged observation.\n"
        raise AssertionError("unreachable")

    def execute(self, decision, proposal):
        wanted = "student" if decision["mode"] == "student" else "gpt_eef"
        if self.source != wanted:
            self.rpc("switch_control_source", source=wanted, reason=decision["reason"])
            self.source = wanted
        # Preserve the baseline 16-step replan cadence across the server's 15-step RPC cap.
        if wanted == "student":
            groups = [
                proposal.actions[i : min(i + 15, decision["steps"])]
                for i in range(0, decision["steps"], 15)
            ]
        else:
            groups = [None] * decision["steps"]
        ended = False
        start_step = self.step
        executed = []
        for actions in groups:
            if actions is None:
                ik = self.rpc("eef_joint_target", targets=decision["target"])
                actions = np.asarray([ik["action"]], dtype=np.float32)
            ack = self.rpc("chunk_step", actions=actions, teacher_request_id=decision["request_id"])
            self.step = ack["step_id"]
            self.control_steps += len(ack["steps"])
            executed.extend(ack["steps"])
            if wanted != "student":
                self.correction_steps += len(ack["steps"])
            ended = any(row["terminated"] or row["truncated"] for row in ack["steps"])
            self.trace.append(
                "execution_ack",
                {
                    "step_id": self.step,
                    "executed_steps": len(ack["steps"]),
                    "mode": decision["mode"],
                    "terminated_or_truncated": ended,
                },
            )
            if ended:
                break
        grippers = []
        for row in executed:
            action = row.get("executed_action")
            if action is not None and len(action) >= 14:
                grippers.append([round(float(action[6]), 6), round(float(action[13]), 6)])
        self.previous_execution = {
            "start_step": start_step,
            "end_step": self.step,
            "mode": decision["mode"],
            "executed_steps": len(executed),
            "gripper_opening_commands_left_right": grippers,
            "terminated_or_truncated": ended,
        }
        return ended

    def run(self):
        started = time.monotonic()
        self.meta = self.sim.request("metadata")
        if self.meta["task"] != self.case["runtime_task"]:
            raise ContractError("simulator task differs from frozen case")
        reset = self.sim.request(
            "reset",
            seed=self.case["layout_id"],
            source="student" if self.policy else "gpt_eef",
            policy_version=self.method,
        )
        self.episode, self.step = reset["episode_id"], reset["step_id"]
        self.trace.append("reset", reset)
        save_json(self.output / "method-profile.json", self.method_profile)
        self.trace.append("method_profile", self.method_profile)
        from hybrid_rollout.robodojo.prompt_context import task_context

        self.task_context = task_context(self.case["runtime_task"])
        self.rpc(
            "begin_combination",
            evaluation_method=self.method,
            teacher_model="gpt-6-astra" if self.reasoner else None,
            teacher_reasoning_effort="xhigh" if self.reasoner else None,
            prompt_sha256=hashlib.sha256(
                (PROMPT + (HYBRID if self.policy else DIRECT)).encode()
            ).hexdigest()
            if self.reasoner
            else None,
            student_policy_version="qwenpi_v3" if self.policy else None,
        )
        try:
            while True:
                obs, images, current = self.observe()
                if not self.history:
                    self.initial_eef = current
                request = {
                    "request_id": uuid.uuid4().hex,
                    "task": self.meta["task"],
                    "instruction": obs["instruction"],
                    "step_id": self.step,
                    "remaining_steps": obs["remaining_steps"],
                    "current_eef": current,
                    "current_state": obs["states"].tolist(),
                    "max_episode_steps": self.meta["max_episode_steps"],
                }
                if self.previous_execution is not None:
                    request["previous_execution"] = self.previous_execution
                proposal = self.propose(obs) if self.policy else None
                if self.method == "qwenpi_v3":
                    decision = {
                        "request_id": request["request_id"],
                        "mode": "student",
                        "steps": self.baseline_action_steps,
                        "reason": f"QwenPI_v3 execute horizon {self.baseline_action_steps}",
                    }
                else:
                    if proposal is not None:
                        preview = self.rpc("fk_preview", actions=proposal.actions)
                        request["student_eef_trajectory"] = compact_eef_trajectory(
                            preview["trajectory"]
                        )
                        request["action_diagnostics"] = proposal.metadata["diagnostics"]
                        request["fk_check"] = preview.get("measured_fk_check")
                    decision = self.reason(request, images, proposal is not None)
                save_json(self.output / f"request_{len(self.history):05d}.json", request)
                self.trace.append("selected_action", decision)
                # Record method identity truthfully; never inherit the upstream pi05 label.
                if self.reasoner:
                    self.rpc(
                        "record_codex_decision",
                        decision=len(self.history),
                        prediction_id=proposal.proposal_id if proposal else None,
                        response=dict(decision, evaluation_method=self.method),
                    )
                ended = self.execute(decision, proposal)
                self.history.append(
                    {
                        "step_id": self.step,
                        "mode": decision["mode"],
                        "steps": decision["steps"],
                        "reason": decision["reason"],
                    }
                )
                self.previous_images = images
                metrics = {
                    "step_id": self.step,
                    "decisions": len(self.history),
                    "reasoner_calls": self.calls,
                    "usage": self.usage,
                    "reasoner_seconds": self.reasoner_seconds,
                    "policy_calls": self.policy_calls,
                    "policy_seconds": self.policy_seconds,
                    "correction_steps": self.correction_steps,
                    "control_steps": self.control_steps,
                    "wall_seconds": time.monotonic() - started,
                }
                save_json(self.output / "progress.json", metrics)
                print(
                    json.dumps(
                        dict(
                            event="progress",
                            method=self.method,
                            case_id=self.case["case_id"],
                            **metrics,
                        )
                    ),
                    flush=True,
                )
                if ended or (self.smoke_decisions and len(self.history) >= self.smoke_decisions):
                    result = self.rpc(
                        "finish_pilot", reason="terminal" if ended else "smoke_budget"
                    )
                    save_json(self.output / "result.json", dict(result, **metrics))
                    return result
        except BaseException:
            if self.sim.sock is not None:
                self.rpc("finish_pilot", reason="controller_error")
            raise
