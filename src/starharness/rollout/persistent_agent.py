"""One persistent Codex thread, policy-neutral tools, and physical-progress limits."""

import hashlib
import json
import time
from pathlib import Path

from hybrid_rollout.robodojo.io import InputError
from hybrid_rollout.robodojo.skill.run import content_items, toml_value, tool_specs
from hybrid_rollout.robodojo.skill.transport import StdioAppServer

from .controller import save_json
from .provider_failure import classify_provider_error
from .public_workspace import prepare_public_workspace


def uncached_tokens(usage):
    return max(0, usage.get("totalTokens", 0) - usage.get("cachedInputTokens", 0))


def specs(direct):
    tools = tool_specs("gpt_only" if direct else "pi05_plus_gpt")
    for tool in tools:
        if tool["name"] == "pi05_infer":
            tool["name"] = "policy_infer"
        tool["description"] = tool["description"].replace("pi05", "QwenPI_v3")
    return tools


class PersistentAgent:
    def __init__(self, output, executable, *, prompt, provider, direct=False,
                 no_action_seconds=600, no_action_tokens=250000,
                 transport_factory=StdioAppServer, task=None,
                 app_server_timeout=180, reasoner_restart_attempts=0):
        if no_action_seconds <= 0 or no_action_tokens <= 0:
            raise ValueError("physical-progress budgets must be positive")
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.agent = prepare_public_workspace(self.output, direct=direct, task=task)
        self.direct, self.provider = direct, provider
        self.no_action_seconds, self.no_action_tokens = no_action_seconds, no_action_tokens
        if app_server_timeout <= 0 or app_server_timeout > 600:
            raise ValueError("app_server_timeout must be between 0 and 600 seconds")
        if reasoner_restart_attempts < 0 or reasoner_restart_attempts > 5:
            raise ValueError("reasoner_restart_attempts must be between 0 and 5")
        self.app_server_timeout = app_server_timeout
        self.reasoner_restart_attempts = int(reasoner_restart_attempts)
        workspace_prompt = (
            prompt
            + "\n\nWorkspace contract: your cwd is the agent workspace. Read AGENTS.md, "
            "workspace.json, SKILL.md and context/teacher_context.md before control. "
            "Keep durable episode memory in NOTES.md."
            + "\n\n" + (self.agent / "SKILL.md").read_text()
            + "\n\n" + (self.agent / "context/teacher_context.md").read_text()
        )
        self.prompt_sha256 = hashlib.sha256(workspace_prompt.encode()).hexdigest()
        (self.output / "prompt.txt").write_text(workspace_prompt, encoding="utf-8")
        (self.output / "public_reasoning.jsonl").touch(mode=0o600)
        self.usage = {}
        config = {
            "model": "gpt-6-astra", "model_reasoning_effort": "xhigh",
            "model_provider": provider, "default_permissions": "unity_rollout",
            "permissions.unity_rollout.extends": ":workspace",
            "permissions.unity_rollout.filesystem": {
                str(self.output.parent): "read", str(self.agent): "write"},
            "features.shell_tool": True, "features.view_image": True,
            "features.multi_agent": False, "features.goals": False,
            "features.sleep_tool": False, "features.apps": False,
            "features.plugins": False, "web_search": "disabled",
            "sqlite_home": str(self.output / "runtime_db"),
            "log_dir": str(self.output / "runtime_logs"),
        }
        command = [executable, "app-server", "--stdio"]
        for key, value in config.items():
            command.extend(["-c", key + "=" + toml_value(value)])
        save_json(self.output / "config.json", config)
        self.transport = transport_factory(command, self.output)
        try:
            self.transport.request("initialize", {
                "clientInfo": {"name": "unity-policy", "version": "1"},
                "capabilities": {"experimentalApi": True}}, app_server_timeout)
            self.transport.notify("initialized", {})
            result = self.transport.request("thread/start", {
                "cwd": str(self.agent), "model": "gpt-6-astra", "modelProvider": provider,
                "config": {"model_reasoning_effort": "xhigh"},
                "developerInstructions": workspace_prompt, "dynamicTools": specs(direct),
                "ephemeral": False, "allowProviderModelFallback": False,
                "approvalPolicy": "never", "permissions": "unity_rollout",
                "runtimeWorkspaceRoots": [str(self.agent)]}, app_server_timeout)
            if result.get("model") != "gpt-6-astra" or result.get("reasoningEffort") != "xhigh":
                raise RuntimeError("app-server model/effort handshake mismatch")
            self.thread = result["thread"]["id"]
            save_json(self.output / "identity.json", {
                "thread_id": self.thread, "requested_model": "gpt-6-astra",
                "requested_effort": "xhigh", "provider": provider,
                "upstream_identity_verified": False, "prompt_sha256": self.prompt_sha256,
                "no_action_seconds": no_action_seconds, "no_action_tokens": no_action_tokens,
                "reasoner_restart_attempts": self.reasoner_restart_attempts,
                "reasoning_evidence": {
                    "private_chain_of_thought_available": False,
                    "public_decision_records": "public_reasoning.jsonl",
                    "raw_app_server_events": "rpc_out.jsonl",
                },
                "workspace_contract": "starharness.agent_workspace.v2",
                "workspace_manifest_sha256": hashlib.sha256(
                    (self.agent / "workspace.json").read_bytes()).hexdigest(),
                "category_completion_policy": "ledger_and_verify_before_switch",
            })
            save_json(self.output / "budget.json", {
                "token_measure": "uncached_input_plus_output",
                "no_action_tokens": no_action_tokens, "no_action_seconds": no_action_seconds})
        except BaseException:
            self.transport.close()
            raise

    def run(self, rollout):
        started = time.monotonic()
        handler_seconds = policy_seconds = 0.0
        turn_params = {
            "threadId": self.thread, "model": "gpt-6-astra", "effort": "xhigh",
            "approvalPolicy": "never", "permissions": "unity_rollout",
            "cwd": str(self.agent), "runtimeWorkspaceRoots": [str(self.agent)],
        }
        def start_turn(text):
            params = dict(turn_params, input=[{"type": "text", "text": text}])
            result = self.transport.request("turn/start", params, 60)
            return result["turn"]["id"]

        result = self.transport.request("turn/start", dict(turn_params, input=[{
            "type": "text", "text": "Read the workspace contract, then control "
                       "this one episode. First rollout call: "
                       + json.dumps(rollout.next_call())}] ), 60)
        turn = result["turn"]["id"]
        deadline = time.monotonic() + self.no_action_seconds
        last_tokens = 0
        progress_boundary_pending = False
        count = 0
        recovery_attempts = 0
        recovery_serial = 0
        handlers = {"robodojo_start": rollout.start}
        handlers.update({"robodojo_act": rollout.act} if self.direct else {
            "policy_infer": rollout.infer, "robodojo_execute": rollout.execute})
        while rollout.phase != "done":
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("No acknowledged physical progress within configured budget")
            event = self.transport.next_message(remaining)
            method, params = event.get("method"), event.get("params", {})
            if params.get("threadId") not in (None, self.thread):
                raise RuntimeError("Unexpected thread in dedicated app-server")
            if method == "thread/tokenUsage/updated":
                self.usage = params.get("tokenUsage", {}).get("total", {})
                save_json(self.output / "usage.json", self.usage)
                current_tokens = uncached_tokens(self.usage)
                # App-server usually reports usage immediately after a host-tool
                # reply.  The reply itself is the progress boundary, but its usage
                # event may still contain all tokens from the just-finished turn.
                # Establish the baseline at that event instead of charging the
                # fresh policy review against the previous physical chunk.
                if progress_boundary_pending:
                    last_tokens = current_tokens
                    progress_boundary_pending = False
                elif current_tokens - last_tokens >= self.no_action_tokens:
                    raise RuntimeError("No-action token budget exhausted")
            elif method == "item/tool/call":
                if params.get("turnId") != turn:
                    raise RuntimeError("Tool call belongs to another turn")
                name, arguments = params["tool"], params["arguments"]
                save_json(self.output / f"tool_{count:05d}_request.json", params)
                previous_tick = rollout.tick
                handler_started = time.monotonic()
                try:
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except ValueError as error:
                            raise InputError("Tool arguments must be JSON") from error
                    if name not in handlers or not isinstance(arguments, dict):
                        raise InputError("Unknown tool or non-object arguments")
                    packet = handlers[name](**arguments)
                    success = True
                except InputError as error:
                    success = False
                    packet = {"error": str(error), "no_execution": True,
                              "next_call": rollout.next_call()}
                handler_seconds += time.monotonic() - handler_started
                if success and name == "policy_infer":
                    policy_seconds += packet.get("inference_seconds", 0)
                save_json(self.output / f"tool_{count:05d}_result.json", packet)
                # An uncertain transport reply is fatal: never repeat the handler.
                self.transport.reply(
                    event["id"],
                    {
                        "success": success,
                        "contentItems": content_items(
                            packet, images=success and name != "policy_infer"
                        ),
                    },
                )
                count += 1
                if rollout.tick > previous_tick:
                    deadline = time.monotonic() + self.no_action_seconds
                # A fresh policy inference, a validated execution (including a
                # no_execution rejection), and episode start are all acknowledged
                # host progress.  They must not be mistaken for a stalled model
                # merely because the next asynchronous usage update is large.
                progress_boundary_pending = True
                if hasattr(rollout, "output"):
                    counters = rollout.counters
                    save_json(rollout.output / "progress.json", {
                        "step_id": rollout.tick, "decisions": len(rollout.history),
                        "reasoner_calls": 1 + recovery_attempts,
                        "reasoner_call_unit": "persistent_model_turn",
                        "reasoner_seconds": time.monotonic() - started - handler_seconds,
                        "policy_calls": counters.get("predictions", 0),
                        "policy_seconds": policy_seconds, "control_steps": rollout.tick,
                        "correction_steps": counters.get("edited_steps", 0)
                        + counters.get("recovery_steps", 0) + counters.get("gpt_eef_steps", 0),
                        "wall_seconds": time.monotonic() - started,
                        "usage": {"input_tokens": self.usage.get("inputTokens", 0),
                                  "cached_input_tokens": self.usage.get("cachedInputTokens", 0),
                                  "output_tokens": self.usage.get("outputTokens", 0)},
                    })
                print(json.dumps({"event": "persistent_tool", "tool": name,
                                  "step_id": rollout.tick, "success": success}), flush=True)
            elif method == "item/completed":
                item = params.get("item", {})
                if item.get("type") == "agentMessage" and item.get("text"):
                    record = {
                        "thread_id": self.thread,
                        "turn_id": params.get("turnId"),
                        "item_id": item.get("id"),
                        "phase": item.get("phase"),
                        "text": item["text"],
                        "completed_at_ms": params.get("completedAtMs"),
                    }
                    with (self.output / "public_reasoning.jsonl").open("a") as stream:
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            elif method == "turn/completed":
                if params.get("turn", {}).get("id") == turn and rollout.phase != "done":
                    raise RuntimeError("Agent turn ended before native episode termination")
            elif method in ("error", "turn/failed"):
                if params.get("willRetry"):
                    continue
                detail = params.get("error", {})
                failure = classify_provider_error(detail)
                if (failure["recoverable_turn"]
                        and recovery_attempts < self.reasoner_restart_attempts):
                    old_turn = turn
                    recovery_attempts += 1
                    recovery_serial += 1
                    delay = min(8, 2 ** (recovery_attempts - 1))
                    record = {
                        "schema": "unity_policy.provider_recovery.v1",
                        "thread_id": self.thread,
                        "previous_turn_id": old_turn,
                        "categories": failure["categories"],
                        "message": failure["message"],
                        "attempt": recovery_attempts,
                        "step_id": rollout.tick,
                        "phase": rollout.phase,
                        "physical_actions_replayed": 0,
                        "status": "waiting",
                        "delay_seconds": delay,
                    }
                    recovery_path = self.output / f"provider_recovery_{recovery_serial:04d}.json"
                    save_json(recovery_path, record)
                    print(json.dumps({"event": "provider_recovery_wait", **record}), flush=True)
                    time.sleep(delay)
                    text = (
                        "Continue the same RoboDojo episode after a transient provider capacity "
                        "failure. The controller state and acknowledged tool results are "
                        "authoritative. Do not reset the simulator or repeat any tool call "
                        "whose result was already acknowledged. Inspect the latest observation "
                        "and use the next_call below: " + json.dumps(rollout.next_call())
                    )
                    if getattr(rollout, "observation_path", None):
                        text += "\nLatest observation path: " + str(rollout.observation_path)
                    record.update(status="turn_start_requested", next_call=rollout.next_call())
                    save_json(recovery_path, record)
                    try:
                        turn = start_turn(text)
                    except BaseException as error:
                        record.update(
                            status="turn_start_failed", restart_error=type(error).__name__
                        )
                        save_json(recovery_path, record)
                        raise
                    record.update(status="continued", new_turn_id=turn)
                    save_json(recovery_path, record)
                    print(json.dumps({"event": "provider_recovery_continued",
                                      "thread_id": self.thread, "old_turn_id": old_turn,
                                      "turn_id": turn, "step_id": rollout.tick}), flush=True)
                    deadline = time.monotonic() + self.no_action_seconds
                    continue
                # Keep the stable outer exception type for campaign accounting, but
                # carry the provider's safe diagnostic into error.json/monitor output.
                # This avoids making operators inspect raw RPC logs just to tell a
                # quota exhaustion from a transport or model failure.
                message = failure["message"]
                raise RuntimeError(
                    "Codex turn failed"
                    + (f": {message}" if message else "; inspect private transport evidence")
                )
            elif "id" in event and method:
                raise RuntimeError(f"Unexpected capability request: {method}")

    def close(self):
        self.transport.close()
