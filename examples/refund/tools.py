"""退款示例：用 guard 包裹有副作用的工具。"""

from __future__ import annotations

from agentreplayguard import Scenario
from agentreplayguard.services.refund import Refund, SimulatedRefundService


def make_tools(scenario: Scenario):
    service = SimulatedRefundService()

    @scenario.guard().effect("refund", key="refund_id", idempotency_key="idempotency_key")
    def refund(refund_id: str, amount_cents: int, idempotency_key: str | None = None) -> Refund:
        return service.refund(refund_id, amount_cents, idempotency_key)

    @scenario.guard().effect("notify", key="refund_id")
    def notify(refund_id: str) -> str:
        return f"notified {refund_id}"

    return refund, notify, service
