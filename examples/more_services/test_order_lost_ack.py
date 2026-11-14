"""订单模拟服务的 lost-ack 重复副作用检测示例。

展示「模拟服务 + guard 装饰 + 确定性故障注入 + NoDuplicateEffects」的完整闭环，
与退款示例同构，可仿照接入其它外部服务模拟。
"""

from __future__ import annotations

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario
from agentreplayguard.services.order import SimulatedOrderService


def test_order_lost_ack_detected():
    scenario = Scenario(
        "order-lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="order", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("order")],
    )
    service = SimulatedOrderService()
    guard = scenario.guard()

    @guard.effect("order", key="order_id", idempotency_key="idempotency_key")
    def create_order(order_id: str, amount_cents: int, idempotency_key: str | None = None):
        return service.create_order(order_id, amount_cents, idempotency_key)

    # 业务侧重试：提交后超时 → 重试
    for _ in range(2):
        try:
            create_order("ORD-1", 1000)
        except TimeoutError:
            continue

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("order") == 2
    assert service.count() == 2  # 账本确实提交了两次
