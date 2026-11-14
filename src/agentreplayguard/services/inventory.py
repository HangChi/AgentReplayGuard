"""库存模拟服务：内存账本 + 幂等键语义。"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import IdempotencyConflict, _Ledger

__all__ = ["IdempotencyConflict", "InventoryOp", "SimulatedInventoryService"]


@dataclass(frozen=True)
class InventoryOp:
    sku: str
    operation: str
    quantity: int
    idempotency_key: str | None
    committed_tick: int
    ledger_sequence: int


class SimulatedInventoryService:
    """参考实现：内存库存操作账本，支持可开关的幂等键。"""

    def __init__(self) -> None:
        self._ledger: _Ledger[InventoryOp] = _Ledger()

    def apply(
        self,
        sku: str,
        operation: str,
        quantity: int,
        idempotency_key: str | None = None,
    ) -> InventoryOp:
        tick = self._ledger.next_tick()
        if idempotency_key is not None:
            existing = self._ledger.lookup(idempotency_key)
            if existing is not None:
                if (
                    existing.sku == sku
                    and existing.operation == operation
                    and existing.quantity == quantity
                ):
                    return existing
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} reused with different params"
                )

        op = InventoryOp(
            sku=sku,
            operation=operation,
            quantity=quantity,
            idempotency_key=idempotency_key,
            committed_tick=tick,
            ledger_sequence=self._ledger.size + 1,
        )
        self._ledger.register(idempotency_key, op)
        return op

    def by_idempotency_key(self, idempotency_key: str) -> InventoryOp | None:
        return self._ledger.lookup(idempotency_key)

    def count(self) -> int:
        return self._ledger.size
