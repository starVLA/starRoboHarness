import pytest

pytest.importorskip("hybrid_rollout.robodojo.skill.run")
from starroboharness.rollout.persistent_agent import PersistentAgent, specs, uncached_tokens


def test_cached_reuse_is_not_counted_as_new_no_action_tokens():
    assert uncached_tokens({"totalTokens": 293028, "cachedInputTokens": 201216}) == 91812


class Transport:
    def __init__(self, command, output):
        self.replies = []
        self.closed = False
        self.events = []

    def request(self, method, params, timeout):
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


def test_token_growth_without_actions_aborts(tmp_path):
    worker = agent(tmp_path)
    worker.transport.events = [{"method": "thread/tokenUsage/updated", "params": {
        "threadId": "t", "tokenUsage": {"total": {"totalTokens": 250001}}}}]
    rollout = Rollout()
    with pytest.raises(RuntimeError, match="No-action token budget"):
        worker.run(rollout)
    assert rollout.calls == 0


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
