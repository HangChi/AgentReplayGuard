"""Effect Store：副作用尝试的事实记录与查询。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, runtime_checkable

from .clock import counter_id
from .faults import FaultKind


class EffectStatus(str, Enum):
    ATTEMPTED = "attempted"
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EffectRecord:
    effect_id: str
    sequence: int
    effect_type: str
    business_key: str
    params_hash: str
    idempotency_key_hash: str | None
    attempt: int
    status: EffectStatus
    fault: FaultKind | None
    error_type: str | None
    error_message: str | None
    run_id: str | None
    thread_id: str | None
    checkpoint_id: str | None
    started_tick: int
    ended_tick: int | None
    branch_id: str | None = None


def commit_identity(record: EffectRecord) -> tuple[str, str, str]:
    """返回该 COMMITTED 记录的「提交身份」，用于业务提交去重。

    有幂等键时按 (effect_type, business_key, idempotency_key_hash) 去重；
    无幂等键时每条记录独立（用 effect_id 区分）。
    """
    if record.idempotency_key_hash is not None:
        return (record.effect_type, record.business_key, record.idempotency_key_hash)
    return (record.effect_type, record.business_key, record.effect_id)


@runtime_checkable
class EffectView(Protocol):
    @property
    def records(self) -> tuple[EffectRecord, ...]: ...

    def for_effect(self, effect_type: str) -> tuple[EffectRecord, ...]: ...

    def for_key(self, effect_type: str, business_key: str) -> tuple[EffectRecord, ...]: ...

    def committed_count(self, effect_type: str | None = None) -> int: ...


class EffectStore:
    """场景隔离的内存 effect 账本。只追加；写入由 EffectGuard 完成。"""

    def __init__(self) -> None:
        self._records: list[EffectRecord] = []
        self._attempts: dict[tuple[str, str], int] = {}
        self._sequence = 0
        self._effect_counter = 0

    @property
    def records(self) -> tuple[EffectRecord, ...]:
        return tuple(self._records)

    def for_effect(self, effect_type: str) -> tuple[EffectRecord, ...]:
        return tuple(r for r in self._records if r.effect_type == effect_type)

    def for_key(self, effect_type: str, business_key: str) -> tuple[EffectRecord, ...]:
        return tuple(
            r
            for r in self._records
            if r.effect_type == effect_type and r.business_key == business_key
        )

    def committed_count(self, effect_type: str | None = None) -> int:
        identities = {
            commit_identity(r)
            for r in self._records
            if r.status is EffectStatus.COMMITTED
            and (effect_type is None or r.effect_type == effect_type)
        }
        return len(identities)

    def attempts(self, effect_type: str, business_key: str) -> int:
        return self._attempts.get((effect_type, business_key), 0)

    # 公开记账接口（供 EffectGuard 与适配器/测试使用；identity 由账本统一分配）
    def next_attempt(self, effect_type: str, business_key: str) -> int:
        """登记一次新的尝试，返回递增后的 attempt 序号（从 1 起）。"""
        key = (effect_type, business_key)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        return self._attempts[key]

    def append(self, record: EffectRecord) -> EffectRecord:
        """追加一条 effect 记录并分配 effect_id / sequence。

        入参的 ``effect_id`` 与 ``sequence`` 视为占位值（请传空串与 0），
        由账本在此统一分配，保证 identity 口径一致；返回补全后的正式记录。
        """
        self._effect_counter += 1
        self._sequence += 1
        record = replace(
            record,
            effect_id=counter_id("eff", self._effect_counter, 6),
            sequence=self._sequence,
        )
        self._records.append(record)
        return record
