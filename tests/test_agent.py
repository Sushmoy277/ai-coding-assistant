"""Agent loop tests with a fake Claude client (no API calls, no API key needed)."""

from types import SimpleNamespace

import pytest

from assistant.agent import Agent
from assistant.tools import Workspace


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, tool_input):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=tool_input)


def reply(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


class FakeClient:
    """Returns queued responses and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Copy the message list: the agent keeps appending to the same list.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    return Workspace(tmp_path, approve=lambda _d: True)


def make_agent(ws, client):
    return Agent(ws, client=client, on_text=lambda _t: None)


def test_plain_answer(ws):
    client = FakeClient(reply("end_turn", text("Hello!")))
    assert make_agent(ws, client).ask("hi") == "Hello!"
    assert len(client.requests) == 1


def test_tool_call_round_trip(ws):
    client = FakeClient(
        reply("tool_use", text("Let me look."), tool_use("t1", "str_replace_based_edit_tool", {"command": "view", "path": "app.py"})),
        reply("end_turn", text("app.py sets x to 1.")),
    )
    agent = make_agent(ws, client)
    assert agent.ask("what's in app.py?") == "app.py sets x to 1."

    second = client.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    [result] = second[2]["content"]
    assert result["tool_use_id"] == "t1"
    assert "x = 1" in result["content"]
    assert result["is_error"] is False


def test_parallel_tool_results_go_in_one_message(ws):
    client = FakeClient(
        reply(
            "tool_use",
            tool_use("a", "bash", {"command": "echo one"}),
            tool_use("b", "bash", {"command": "echo two"}),
        ),
        reply("end_turn", text("done")),
    )
    make_agent(ws, client).ask("run both")
    results = client.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


def test_refusal_drops_the_turn(ws):
    client = FakeClient(reply("refusal"))
    agent = make_agent(ws, client)
    assert "declined" in agent.ask("something")
    assert agent.messages == []


def test_request_uses_fallbacks_and_effort(ws):
    client = FakeClient(reply("end_turn", text("ok")))
    Agent(ws, client=client, effort="medium", on_text=lambda _t: None).ask("hi")
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default"
    assert req["output_config"] == {"effort": "medium"}
