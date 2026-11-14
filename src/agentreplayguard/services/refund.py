"""退款模拟服务：内存账本 + 幂等键语义。"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import IdempotencyConflict, _Ledger

__all__ = ["IdempotencyConflict", "Refund", "SimulatedRefundService"]


@dataclass(frozen=True)
class Refund:
    refund_id: str
    amount_cents: int
    idempotency_key: str | None
    committed_tick: int
    ledger_sequence: int


class SimulatedRefundService:
    """参考实现：内存退款账本，支持可开关的幂等键。"""

    def __init__(self) -> None:
        self._ledger: _Ledger[Refund] = _Ledger()
        self._by_id: dict[str, Refund] = {}

    def refund(
        self,
        refund_id: str,
        amount_cents: int,
        idempotency_key: str | None = None,
    ) -> Refund:
        tick = self._ledger.next_tick()
        if idempotency_key is not None:
            existing = self._ledger.lookup(idempotency_key)
            if existing is not None:
                if existing.refund_id == refund_id and existing.amount_cents == amount_cents:
                    return existing
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} reused with different params"
                )

        refund = Refund(
            refund_id=refund_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            committed_tick=tick,
            ledger_sequence=self._ledger.size + 1,
        )
        self._ledger.register(idempotency_key, refund)
        self._by_id[refund_id] = refund
        return refund

    def by_refund_id(self, refund_id: str) -> Refund | None:
        return self._by_id.get(refund_id)

    def by_idempotency_key(self, idempotency_key: str) -> Refund | None:
        return self._ledger.lookup(idempotency_key)

    def count(self) -> int:
        return self._ledger.size
