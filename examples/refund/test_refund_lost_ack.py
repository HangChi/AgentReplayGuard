"""US1 独立验收：lost-ack 导致重复退款被检测出来。"""

from __future__ import annotations

import pytest

from agentreplayguard import EffectSafetyError, EffectStatus

from .graph import build_graph
from .tools import make_tools


def test_duplicate_is_detected(lost_ack_scenario, retry_policy):
    refund, notify, service = make_tools(lost_ack_scenario)
    graph = build_graph(refund, notify, retry_policy=retry_policy)

    graph.invoke({"refund_id": "R-1", "amount_cents": 100})

    report = lost_ack_scenario.finish()
    assert not report.ok

    committed_refunds = [
        r
        for r in report.effects
        if r.effect_type == "refund" and r.status is EffectStatus.COMMITTED
    ]
    assert len(committed_refunds) == 2
    # 账本里确实有两笔退款
    assert service.count() == 2


@pytest.mark.xfail(raises=EffectSafetyError, strict=True)
def test_lost_ack_demo_fails(lost_ack_scenario, retry_policy):
    refund, notify, _service = make_tools(lost_ack_scenario)
    graph = build_graph(refund, notify, retry_policy=retry_policy)

    graph.invoke({"refund_id": "R-1", "amount_cents": 100})
    lost_ack_scenario.finish().assert_clean()
