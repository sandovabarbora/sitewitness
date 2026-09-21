from conftest import text, tool

from sitewitness.protocol import DECLINE


def test_text_only_answer_is_enforced_for_no_tool_use(agent_factory):
    agent, client = agent_factory([text("The site has three spots.\nSources: data/surf.json")])
    a = agent.ask("how many spots?")
    assert a.trace.enforced == "require_tool_use" and a.text.startswith(DECLINE)
    assert a.trace.turns == 1 and a.trace.input_tokens == 100 and a.trace.output_tokens == 20
    assert (
        a.trace.cost_usd == round((100 * 1.0 + 20 * 10.0) / 1e6, 5)
        and a.trace.budget_spent_usd == a.trace.cost_usd
    )
    assert a.trace.model_used == "test-model-2026"


def test_tool_use_runs_the_tool_and_answers(agent_factory):
    agent, client = agent_factory(
        [
            tool("read_data", {"source": "data/surf.json", "path": "skill.x.m.1.n"}),
            text("There are 14 pairs at lead 1.\nSources: data/surf.json"),
        ]
    )
    a = agent.ask("pairs at lead 1?")
    assert a.text.startswith("There are 14") and a.trace.enforced is None
    assert [t.name for t in a.trace.tools] == ["read_data"] and a.trace.tools[0].bytes > 0
    # the tool result reached the model on the second call
    second = client.calls[1]["messages"]
    assert (
        second[-1]["role"] == "user"
        and second[-1]["content"][0]["type"] == "tool_result"
        and "14" in second[-1]["content"][0]["content"]
    )
    assert a.trace.numbers_from_tools is True and a.trace.turns == 2


def test_cap_forces_a_final_turn_without_tools(agent_factory):
    script = [tool("list_sources", {}, tid=f"t{i}") for i in range(3)] + [
        tool("list_sources", {}, tid="t9"),
        text(DECLINE + " Nothing more."),
    ]
    agent, client = agent_factory(script, limits={"max_tool_calls": 3})
    a = agent.ask("loop forever")
    assert a.trace.stop == "tool_cap" and len(a.trace.tools) == 3
    assert (
        client.calls[-1]["tools"] is None
        and "Tool budget reached" in client.calls[-1]["messages"][-1]["content"]
    )
    assert a.trace.declined and a.trace.enforced is None


def test_quote_counts(agent_factory):
    agent, _ = agent_factory(
        [
            tool("search", {"query": "wall"}, tid="s1"),
            tool("quote", {"passage_id": "a#1", "phrase": "IAM is a wall"}, tid="q1"),
            text(
                'The text says "a prompt is a suggestion, IAM is a wall, and that is the whole point".\nSources: /texts/a'
            ),
        ]
    )
    a = agent.ask("quote the wall sentence")
    assert (
        a.trace.quotes_verified == 1
        and a.trace.enforced is None
        and a.trace.tools[1].result_status == "found"
    )


def test_limits_decline_before_any_model_call(agent_factory):
    agent, client = agent_factory([text("never")], limits={"per_ip_per_hour": 0})
    a = agent.ask("anything", ip="1.2.3.4")
    assert a.trace.limited == "rate" and client.calls == [] and "questions in an hour" in a.text
    agent, client = agent_factory([text("never")], limits={"daily_budget_usd": 0.0})
    a = agent.ask("anything")
    assert a.trace.limited == "budget" and client.calls == []


def test_system_prompt_has_rules_and_no_site_content(agent_factory):
    agent, client = agent_factory([text(DECLINE + " x")])
    agent.ask("hi")
    s = client.calls[0]["system"]
    assert "fixture" in s and "Sources:" in s and "alpha passage" not in s
