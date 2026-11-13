"""fan-out 并行图集成测试：允许运行、分支归属与并行重复检测。"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agentreplayguard import Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter
from agentreplayguard.invariants import NoDuplicateEffects


class State(TypedDict):
    log: Annotated[list[str], operator.add]


def _make_fanout_graph(scenario: Scenario):
    guard = scenario.guard()
    g = StateGraph(State)

    def start(s):
        return {"log": ["start"]}

    def notify(s):
        guard.call("notify", lambda: None, key=lambda _: "USER-1")
        return {"log": ["notify"]}

    def deduct(s):
        guard.call("deduct", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["deduct"]}

    g.add_node("start", start)
    g.add_node("notify", notify)
    g.add_node("deduct", deduct)
    g.add_edge(START, "start")
    g.add_edge("start", "notify")
    g.add_edge("start", "deduct")  # fan-out
    g.add_edge("notify", END)
    g.add_edge("deduct", END)
    return g.compile()


def _make_serial_graph(scenario: Scenario):
    guard = scenario.guard()
    g = StateGraph(State)

    def only(s):
        guard.call("only", lambda: None, key=lambda _: "K-1")
        return {"log": ["only"]}

    g.add_node("only", only)
    g.add_edge(START, "only")
    g.add_edge("only", END)
    return g.compile()


def test_fanout_not_rejected_strict():
    scenario = Scenario("fanout", seed=0)
    adapter = LangGraphAdapter(scenario, _make_fanout_graph(scenario))
    run = adapter.invoke({"log": []})
    assert run.output is not None


def test_fanout_branch_attribution():
    scenario = Scenario("fanout", seed=0)
    adapter = LangGraphAdapter(scenario, _make_fanout_graph(scenario))
    adapter.invoke({"log": []})

    records = scenario.effects.records
    branches = {r.effect_type: r.branch_id for r in records}
    assert branches["notify"] == "notify"
    assert branches["deduct"] == "deduct"


def test_serial_graph_records_node_name():
    """串行图里 effect 也记录产生它的节点名（branch_id = 节点名）。"""
    scenario = Scenario("serial", seed=0)
    adapter = LangGraphAdapter(scenario, _make_serial_graph(scenario))
    adapter.invoke({"log": []})

    record = scenario.effects.records[0]
    assert record.branch_id == "only"


def test_fanout_duplicate_same_key_detected():
    scenario = Scenario("dup", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()
    g = StateGraph(State)

    def b(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["b"]}

    def c(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
        return {"log": ["c"]}

    g.add_node("b", b)
    g.add_node("c", c)
    g.add_edge(START, "b")
    g.add_edge(START, "c")  # fan-out
    g.add_edge("b", END)
    g.add_edge("c", END)

    adapter = LangGraphAdapter(scenario, g.compile())
    adapter.invoke({"log": []})

    report = scenario.finish()
    assert not report.ok
    violation = next(v for v in report.violations if v.invariant_name == "no_duplicate_effects:refund")
    assert violation.actual == 2
    # 两条违规 effect 来自不同分支
    records = scenario.effects.records
    branches = {r.effect_id: r.branch_id for r in records}
    ids = violation.effect_ids
    assert len(ids) == 2
    assert branches[ids[0]] != branches[ids[1]]


def test_fanout_duplicate_same_key_with_idempotency_ok():
    scenario = Scenario("idem", seed=0, invariants=[NoDuplicateEffects("refund")])
    guard = scenario.guard()
    g = StateGraph(State)

    def b(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1", idempotency_key=lambda _: "ik-1")
        return {"log": ["b"]}

    def c(s):
        guard.call("refund", lambda: None, key=lambda _: "ORDER-1", idempotency_key=lambda _: "ik-1")
        return {"log": ["c"]}

    g.add_node("b", b)
    g.add_node("c", c)
    g.add_edge(START, "b")
    g.add_edge(START, "c")
    g.add_edge("b", END)
    g.add_edge("c", END)

    adapter = LangGraphAdapter(scenario, g.compile())
    adapter.invoke({"log": []})

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1


def test_fanout_deterministic_conclusion_and_branch():
    """连跑 20 次，检测结论与 branch 归属一致（追加 sequence 顺序不断言）。"""
    for _ in range(20):
        scenario = Scenario("det", seed=0, invariants=[NoDuplicateEffects("refund")])
        guard = scenario.guard()
        g = StateGraph(State)

        def b(s):
            guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
            return {"log": ["b"]}

        def c(s):
            guard.call("refund", lambda: None, key=lambda _: "ORDER-1")
            return {"log": ["c"]}

        g.add_node("b", b)
        g.add_node("c", c)
        g.add_edge(START, "b")
        g.add_edge(START, "c")
        g.add_edge("b", END)
        g.add_edge("c", END)

        adapter = LangGraphAdapter(scenario, g.compile())
        adapter.invoke({"log": []})
        report = scenario.finish()

        assert not report.ok
        branches = {r.effect_id: r.branch_id for r in scenario.effects.records}
        assert set(branches.values()) == {"b", "c"}
