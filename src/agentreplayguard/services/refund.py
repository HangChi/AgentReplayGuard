"""退款模拟服务：内存账本 + 幂等键语义。"""

from __future__ import annotations

from dataclasses import dataclass


class IdempotencyConflict(Exception):
    """同一幂等键对应不同参数。"""


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
        self._ledger: list[Refund] = []
        self._by_id: dict[str, Refund] = {}
        self._by_key: dict[str, Refund] = {}
        self._counter = 0

    def refund(self, refund_id: str, amount_cents: int, idempotency_key: str | None = None) -> Refund:
        self._counter += 1
        if idempotency_key is not None and idempotency_key in self._by_key:
            existing = self._by_key[idempotency_key]
            if existing.refund_id == refund_id and existing.amount_cents == amount_cents:
                return existing
            raise IdempotencyConflict(
                f"idempotency key {idempotency_key!r} reused with different params"
            )

        refund = Refund(
            refund_id=refund_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            committed_tick=self._counter,
            ledger_sequence=len(self._ledger) + 1,
        )
        self._ledger.append(refund)
        self._by_id[refund_id] = refund
        if idempotency_key is not None:
            self._by_key[idempotency_key] = refund
        return refund

    def by_refund_id(self, refund_id: str) -> Refund | None:
        return self._by_id.get(refund_id)

    def by_idempotency_key(self, idempotency_key: str) -> Refund | None:
        return self._by_key.get(idempotency_key)

    def count(self) -> int:
        return len(self._ledger)
