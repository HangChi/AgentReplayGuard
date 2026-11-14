"""US4 集成测试：interrupt 恢复后的重放安全性。"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from agentreplayguard import NoDuplicateEffects, Scenario, ScenarioConfigError
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _build_interrupt_graph(scenario, *, effect_before_interrupt):
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    def do_refund(state):
        if effect_before_interrupt:
            refund(state["refund_id"], state["amount_cents"])
            interrupt({"approval": "needed"})
        else:
            interrupt({"approval": "needed"})
            refund(state["refund_id"], state["amount_cents"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "__end__")
    return builder.compile(checkpointer=InMemorySaver())


def test_interrupt_after_effect_resume_duplicates():
    scenario = Scenario("interrupt-effect-before", invariants=[NoDuplicateEffects("refund")])
    adapter = LangGraphAdapter(
        scenario, _build_interrupt_graph(scenario, effect_before_interrupt=True)
    )

    run = adapter.invoke({"refund_id": "R-1", "amount_cents": 100})
    assert run.segment.interrupted is True
    assert run.interrupts != ()

    adapter.resume_interrupt({"approved": True})

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2


def test_interrupt_before_effect_resume_no_duplicate():
    scenario = Scenario("interrupt-effect-after", invariants=[NoDuplicateEffects("refund")])
    adapter = LangGraphAdapter(
        scenario, _build_interrupt_graph(scenario, effect_before_interrupt=False)
    )

    run = adapter.invoke({"refund_id": "R-1", "amount_cents": 100})
    assert run.segment.interrupted is True

    adapter.resume_interrupt({"approved": True})

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1


def test_resume_interrupt_requires_interrupted_run():
    scenario = Scenario("no-interrupt")

    def node(state):
        return state

    builder = StateGraph(dict)
    builder.add_node("n", node)
    builder.set_entry_point("n")
    builder.add_edge("n", "__end__")
    adapter = LangGraphAdapter(scenario, builder.compile(checkpointer=InMemorySaver()))

    adapter.invoke({"x": 1})
    with pytest.raises(ScenarioConfigError):
        adapter.resume_interrupt({"x": 1})
