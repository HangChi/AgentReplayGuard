"""US3 独立验收：checkpoint 恢复不会重复执行已完成的副作用。"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter

from .graph import build_graph
from .tools import make_tools


def _resume_scenario(fault_effect: str) -> Scenario:
    return Scenario(
        "refund-resume",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type=fault_effect, attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )


def test_resume_re_executes_effect_before_checkpoint():
    scenario = _resume_scenario("refund")
    refund, notify, service = make_tools(scenario)
    graph = build_graph(refund, notify, checkpointer=InMemorySaver())
    adapter = LangGraphAdapter(scenario, graph)

    with pytest.raises(TimeoutError):
        adapter.invoke({"refund_id": "R-1", "amount_cents": 100})

    adapter.resume()

    report = scenario.finish()
    assert not report.ok
    assert service.count() == 2


def test_resume_does_not_re_execute_effect_after_checkpoint():
    scenario = _resume_scenario("notify")
    refund, notify, service = make_tools(scenario)
    graph = build_graph(refund, notify, checkpointer=InMemorySaver())
    adapter = LangGraphAdapter(scenario, graph)

    with pytest.raises(TimeoutError):
        adapter.invoke({"refund_id": "R-1", "amount_cents": 100})

    adapter.resume()

    report = scenario.finish()
    assert report.ok
    assert service.count() == 1
