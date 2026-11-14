"""订单模拟服务：内存账本 + 幂等键语义。"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import IdempotencyConflict, _Ledger

__all__ = ["IdempotencyConflict", "Order", "SimulatedOrderService"]


@dataclass(frozen=True)
class Order:
    order_id: str
    amount_cents: int
    idempotency_key: str | None
    committed_tick: int
    ledger_sequence: int


class SimulatedOrderService:
    """参考实现：内存订单账本，支持可开关的幂等键。"""

    def __init__(self) -> None:
        self._ledger: _Ledger[Order] = _Ledger()
        self._by_id: dict[str, Order] = {}

    def create_order(
        self,
        order_id: str,
        amount_cents: int,
        idempotency_key: str | None = None,
    ) -> Order:
        tick = self._ledger.next_tick()
        if idempotency_key is not None:
            existing = self._ledger.lookup(idempotency_key)
            if existing is not None:
                if existing.order_id == order_id and existing.amount_cents == amount_cents:
                    return existing
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} reused with different params"
                )

        order = Order(
            order_id=order_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            committed_tick=tick,
            ledger_sequence=self._ledger.size + 1,
        )
        self._ledger.register(idempotency_key, order)
        self._by_id[order_id] = order
        return order

    def by_order_id(self, order_id: str) -> Order | None:
        return self._by_id.get(order_id)

    def by_idempotency_key(self, idempotency_key: str) -> Order | None:
        return self._ledger.lookup(idempotency_key)

    def count(self) -> int:
        return self._ledger.size
