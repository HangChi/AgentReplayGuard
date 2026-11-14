"""模拟服务的共享幂等账本与异常。"""

from __future__ import annotations

from typing import Generic, TypeVar

RecordT = TypeVar("RecordT")


class IdempotencyConflict(Exception):
    """同一幂等键对应不同参数。"""


class _Ledger(Generic[RecordT]):
    """幂等账本核心：顺序登记、幂等键索引与单调计数。

    committed_tick 对每次尝试（含冲突尝试）单调递增；
    ledger_sequence 只对成功提交的记录递增（= 账本长度）。
    """

    def __init__(self) -> None:
        self._items: list[RecordT] = []
        self._by_key: dict[str, RecordT] = {}
        self._counter = 0

    def next_tick(self) -> int:
        """推进尝试计数，返回本次尝试的 committed_tick。"""
        self._counter += 1
        return self._counter

    def lookup(self, idempotency_key: str) -> RecordT | None:
        return self._by_key.get(idempotency_key)

    def register(self, idempotency_key: str | None, record: RecordT) -> None:
        """登记一条成功提交的记录：追加账本，有幂等键则建索引。"""
        self._items.append(record)
        if idempotency_key is not None:
            self._by_key[idempotency_key] = record

    @property
    def size(self) -> int:
        return len(self._items)
