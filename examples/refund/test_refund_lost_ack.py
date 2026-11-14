"""US1 独立验收：lost-ack 导致重复退款被检测出来。"""

from __future__ import annotations

import pytest

from agentreplayguard import (
    EffectSafetyError,
    EffectStatus,
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
)

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


def test_auto_assert_without_any_assertion(replayguard, retry_policy):
    """013 自动断言：不写任何断言，重复退款也会让本测试失败。

    用 `expect_violations=True` 把这个「应当失败」的事实变成可运行的示例——
    去掉该参数后，本测试会因为 2 笔重复退款而 FAILED。
    """
    scenario = replayguard(
        "refund-auto-assert",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
        expect_violations=True,
    )
    refund, notify, service = make_tools(scenario)
    graph = build_graph(refund, notify, retry_policy=retry_policy)

    graph.invoke({"refund_id": "R-1", "amount_cents": 100})

    # 这里故意不写任何断言：若不声明 expect_violations，测试会自动 FAILED。
    assert service.count() == 2
