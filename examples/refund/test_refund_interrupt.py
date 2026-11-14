"""US4 独立验收：interrupt 恢复后的重放安全性。"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from agentreplayguard import NoDuplicateEffects, Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter

from .tools import make_tools


def _build_interrupt_graph(refund, *, effect_before_interrupt):
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


def test_interrupt_after_effect_duplicates():
    scenario = Scenario(
        "refund-interrupt-before", seed=0, invariants=[NoDuplicateEffects("refund")]
    )
    refund, _notify, service = make_tools(scenario)
    graph = _build_interrupt_graph(refund, effect_before_interrupt=True)
    adapter = LangGraphAdapter(scenario, graph)

    adapter.invoke({"refund_id": "R-1", "amount_cents": 100})
    adapter.resume_interrupt({"approved": True})

    report = scenario.finish()
    assert not report.ok
    assert service.count() == 2


def test_interrupt_before_effect_no_duplicate():
    scenario = Scenario("refund-interrupt-after", seed=0, invariants=[NoDuplicateEffects("refund")])
    refund, _notify, service = make_tools(scenario)
    graph = _build_interrupt_graph(refund, effect_before_interrupt=False)
    adapter = LangGraphAdapter(scenario, graph)

    adapter.invoke({"refund_id": "R-1", "amount_cents": 100})
    adapter.resume_interrupt({"approved": True})

    report = scenario.finish()
    assert report.ok
    assert service.count() == 1
