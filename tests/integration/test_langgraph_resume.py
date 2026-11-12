"""US3 集成测试：checkpoint 恢复的重复执行语义。"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _build_graph(scenario):
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id, amount_cents):
        return f"refunded {refund_id}"

    @guard.effect("notify", key="refund_id")
    def notify(refund_id):
        return f"notified {refund_id}"

    def do_refund(state):
        refund(state["refund_id"], state["amount_cents"])
        return state

    def do_notify(state):
        notify(state["refund_id"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    return builder.compile(checkpointer=InMemorySaver())


def test_resume_re_executes_effect_before_checkpoint():
    scenario = Scenario(
        "resume-before",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    adapter = LangGraphAdapter(scenario, _build_graph(scenario))

    with pytest.raises(TimeoutError):
        adapter.invoke({"refund_id": "R-1", "amount_cents": 100})

    adapter.resume()

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    assert [segment.run_id for segment in report.run_segments] == ["run-0001", "run-0002"]


def test_resume_does_not_re_execute_effect_after_checkpoint():
    scenario = Scenario(
        "resume-after",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="notify", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    adapter = LangGraphAdapter(scenario, _build_graph(scenario))

    with pytest.raises(TimeoutError):
        adapter.invoke({"refund_id": "R-1", "amount_cents": 100})

    adapter.resume()

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
    assert [segment.run_id for segment in report.run_segments] == ["run-0001", "run-0002"]
