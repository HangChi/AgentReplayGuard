"""分支归属公开契约测试。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agentreplayguard import Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter
from agentreplayguard.effects import EffectRecord


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def _fanout_graph(scenario: Scenario):
    guard = scenario.guard()
    g = StateGraph(State)

    def b(s):
        guard.call("op", lambda: None, key=lambda _: "k-b")
        return {"log": ["b"]}

    def c(s):
        guard.call("op", lambda: None, key=lambda _: "k-c")
        return {"log": ["c"]}

    g.add_node("b", b)
    g.add_node("c", c)
    g.add_edge(START, "b")
    g.add_edge(START, "c")
    g.add_edge("b", END)
    g.add_edge("c", END)
    return g.compile()


def test_branch_id_field_is_public():
    assert "branch_id" in EffectRecord.__dataclass_fields__


def test_strict_graph_supports_fanout():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, _fanout_graph(scenario))  # strict_graph 默认 True
    adapter.invoke({"log": []})
    assert len(scenario.effects.records) == 2


def test_non_strict_skips_fanout_check_and_warns():
    scenario = Scenario("s")
    adapter = LangGraphAdapter(scenario, _fanout_graph(scenario), strict_graph=False)
    adapter.invoke({"log": []})
    report = scenario.finish()
    assert any("strict_graph" in w for w in report.warnings)
