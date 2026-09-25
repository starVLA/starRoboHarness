import json

import pytest

pytest.importorskip("hybrid_rollout.robodojo.skill.run")
from starharness.rollout.persistent_agent import PersistentAgent, specs, uncached_tokens


def test_cached_reuse_is_not_counted_as_new_no_action_tokens():
    assert uncached_tokens({"totalTokens": 293028, "cachedInputTokens": 201216}) == 91812


class Transport:
    def __init__(self, command, output):
        self.replies = []
        self.closed = False
        self.events = []

    def request(self, method, params, timeout):
        if method == "initialize":
            self.initialize_timeout = timeout
        if method == "thread/start":
            self.thread_params = params
            return {"model": "gpt-6-astra", "reasoningEffort": "xhigh", "thread": {"id": "t"}}
        return {"turn": {"id": "turn"}}

    def notify(self, *args):
        pass

    def next_message(self, timeout):
        return self.events.pop(0)

    def reply(self, identifier, result):
        self.replies.append((identifier, result))

    def close(self):
        self.closed = True


class Rollout:
    tick = 0
    phase = "start"
    calls = 0

    def next_call(self):
        return {"tool": "robodojo_start"}

    def start(self):
        self.calls += 1
        self.tick = 1
        self.phase = "done"
        return {"rollout_finished": True}

    def act(self):
        raise AssertionError("unexpected action")


class BoundaryRollout(Rollout):
    def start(self):
        self.calls += 1
        self.tick = 1
        self.phase = "active"
        return {"started": True}

    def act(self):
        self.calls += 1
        self.tick = 2
        self.phase = "done"
        return {"rollout_finished": True}


class RecoveryTransport(Transport):
    def __init__(self, command, output):
        super().__init__(command, output)
        self.turn_starts = []

    def request(self, method, params, timeout):
        if method == "turn/start":
            self.turn_starts.append(params)
            turn_id = f"turn-{len(self.turn_starts)}"
            return {"turn": {"id": turn_id}}
        return super().request(method, params, timeout)


def agent(tmp_path):
    return PersistentAgent(tmp_path / "agent", "codex", prompt="test", provider="test",
                           direct=True, transport_factory=Transport)


def test_dynamic_tool_is_executed_once_and_thread_is_persistent(tmp_path):
    worker = agent(tmp_path)
    worker.transport.events = [{"id": 4, "method": "item/tool/call", "params": {
        "threadId": "t", "turnId": "turn", "tool": "robodojo_start", "arguments": {}}}]
    rollout = Rollout()
    worker.run(rollout)
    assert rollout.calls == 1
    assert len(worker.transport.replies) == 1
    assert worker.transport.thread_params["ephemeral"] is False
    assert "policy_infer" in [tool["name"] for tool in specs(False)]
    assert "pi05" not in str(specs(False))
    assert worker.transport.initialize_timeout == 180


def test_capacity_restarts_same_thread_without_replaying_tool(tmp_path):
    worker = PersistentAgent(
        tmp_path / "agent", "codex", prompt="test", provider="test", direct=True,
        transport_factory=RecoveryTransport, reasoner_restart_attempts=1,
    )
    worker.transport.events = [
        {"method": "turn/failed", "params": {
            "threadId": "t", "turnId": "turn-1", "willRetry": False,
            "error": {"message": "Selected model is at capacity. Please try again."},
        }},
        {"id": 4, "method": "item/tool/call", "params": {
            "threadId": "t", "turnId": "turn-2", "tool": "robodojo_start", "arguments": {}}},
    ]
    rollout = Rollout()
    worker.run(rollout)
    assert rollout.calls == 1
    assert len(worker.transport.replies) == 1
    assert len(worker.transport.turn_starts) == 2
    recovery = json.loads((worker.output / "provider_recovery_0001.json").read_text())
    assert recovery["status"] == "continued"
    assert recovery["physical_actions_replayed"] == 0
    assert recovery["categories"] == ["capacity"]
    assert recovery["new_turn_id"] == "turn-2"


def test_usage_limit_is_not_restarted(tmp_path):
    worker = PersistentAgent(
        tmp_path / "agent", "codex", prompt="test", provider="test", direct=True,
        transport_factory=RecoveryTransport, reasoner_restart_attempts=2,
    )
    worker.transport.events = [{"method": "turn/failed", "params": {
        "threadId": "t", "turnId": "turn-1", "willRetry": False,
        "error": {"message": "You've hit your usage limit."},
    }}]
    with pytest.raises(RuntimeError, match="usage limit"):
        worker.run(Rollout())
    assert len(worker.transport.turn_starts) == 1


def test_handshake_timeout_is_bounded_and_configurable(tmp_path):
    worker = PersistentAgent(tmp_path / "agent", "codex", prompt="test", provider="test",
                             transport_factory=Transport, app_server_timeout=120)
    assert worker.transport.initialize_timeout == 120
    with pytest.raises(ValueError, match="app_server_timeout"):
        PersistentAgent(tmp_path / "invalid", "codex", prompt="test", provider="test",
                        transport_factory=Transport, app_server_timeout=601)


def test_token_growth_without_actions_aborts(tmp_path):
    worker = agent(tmp_path)
    worker.transport.events = [{"method": "thread/tokenUsage/updated", "params": {
        "threadId": "t", "tokenUsage": {"total": {"totalTokens": 250001}}}}]
    rollout = Rollout()
    with pytest.raises(RuntimeError, match="No-action token budget"):
        worker.run(rollout)
    assert rollout.calls == 0


def test_usage_update_after_acknowledged_tool_starts_new_token_window(tmp_path):
    worker = agent(tmp_path)
    worker.transport.events = [
        {"id": 4, "method": "item/tool/call", "params": {
            "threadId": "t", "turnId": "turn", "tool": "robodojo_start", "arguments": {}}},
        {"method": "thread/tokenUsage/updated", "params": {
            "threadId": "t", "tokenUsage": {"total": {"totalTokens": 300001}}}},
        {"id": 5, "method": "item/tool/call", "params": {
            "threadId": "t", "turnId": "turn", "tool": "robodojo_act", "arguments": {}}},
    ]
    rollout = BoundaryRollout()
    worker.run(rollout)
    assert rollout.calls == 2


def test_uncertain_reply_never_reexecutes_action(tmp_path):
    worker = agent(tmp_path)
    worker.transport.events = [{"id": 4, "method": "item/tool/call", "params": {
        "threadId": "t", "turnId": "turn", "tool": "robodojo_start", "arguments": {}}}]
    def uncertain(*args):
        raise OSError("connection lost after dispatch")
    worker.transport.reply = uncertain
    rollout = Rollout()
    with pytest.raises(OSError):
        worker.run(rollout)
    assert rollout.calls == 1


def test_completed_public_agent_messages_are_exported_for_analysis(tmp_path):
    worker = agent(tmp_path)
    worker.transport.events = [
        {
            "method": "item/completed",
            "params": {
                "threadId": "t",
                "turnId": "turn",
                "completedAtMs": 123,
                "item": {
                    "id": "message-1",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "Evidence: tower leans. Next: verify the right block.",
                },
            },
        },
        {
            "id": 4,
            "method": "item/tool/call",
            "params": {
                "threadId": "t",
                "turnId": "turn",
                "tool": "robodojo_start",
                "arguments": {},
            },
        },
    ]
    worker.run(Rollout())
    rows = (worker.output / "public_reasoning.jsonl").read_text().splitlines()
    assert len(rows) == 1
    assert "tower leans" in rows[0]
