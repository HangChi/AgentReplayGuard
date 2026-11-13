"""流式退款示例：用 astream 驱动图，验证 lost-ack 重复副作用检测。"""

from __future__ import annotations

import asyncio

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario
from agentreplayguard.adapters.langgraph import LangGraphAdapter

from .graph import build_graph
from .tools import make_tools


def test_streaming_lost_ack_detected(retry_policy):
    scenario = Scenario(
        "refund-streaming-lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    refund, notify, _ = make_tools(scenario)
    graph = build_graph(refund, notify, retry_policy=retry_policy)
    adapter = LangGraphAdapter(scenario, graph)

    async def run():
        chunks = []
        async for chunk in adapter.astream({"refund_id": "R-STREAM-1", "amount_cents": 1000}):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(run())

    assert len(chunks) >= 1
    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    # effect 归属正确
    assert all(r.run_id == "run-0001" for r in scenario.effects.for_effect("refund"))
