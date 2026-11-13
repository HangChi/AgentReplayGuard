"""并行退款示例测试：fan-out 分支重复副作用检测。"""

from __future__ import annotations

from agentreplayguard import NoDuplicateEffects, Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter

from .graph_parallel import build_parallel_graph
from .tools import make_tools


def test_parallel_duplicate_detected_without_idempotency():
    scenario = Scenario(
        "parallel-duplicate-refund",
        seed=0,
        invariants=[NoDuplicateEffects("refund")],
    )
    refund, _, _ = make_tools(scenario)
    graph = build_parallel_graph(refund)
    adapter = LangGraphAdapter(scenario, graph)

    adapter.invoke({"refund_id": "R-PAR-1", "amount_cents": 1000, "log": []})

    report = scenario.finish()
    assert not report.ok
    # 两个分支各自提交一次，commit_count = 2
    assert scenario.effects.committed_count("refund") == 2
    # 分支归属不同
    branches = {r.branch_id for r in scenario.effects.for_effect("refund")}
    assert branches == {"refund_a", "refund_b"}


def test_parallel_duplicate_folded_with_idempotency_key():
    scenario = Scenario(
        "parallel-idempotent-refund",
        seed=0,
        invariants=[NoDuplicateEffects("refund")],
    )
    refund, _, _ = make_tools(scenario)
    graph = build_parallel_graph(
        refund,
        idempotency_key_factory=lambda state: f"ik-{state['refund_id']}",
    )
    adapter = LangGraphAdapter(scenario, graph)

    adapter.invoke({"refund_id": "R-PAR-2", "amount_cents": 1000, "log": []})

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
