"""不变量：内置「无重复 effect」「effect 数量上限」与自定义断言。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Protocol

from .effects import EffectRecord, EffectStatus, EffectView, commit_identity
from .errors import ScenarioConfigError


class Invariant(Protocol):
    name: str

    def check(self, view: EffectView) -> list[Violation]: ...


@dataclass(frozen=True)
class Violation:
    invariant_name: str
    message: str
    expected: Any
    actual: Any
    effect_ids: tuple[str, ...]


def _committed(records: tuple[EffectRecord, ...], effect_type: str | None) -> list[EffectRecord]:
    return [
        r
        for r in records
        if r.status is EffectStatus.COMMITTED
        and (effect_type is None or r.effect_type == effect_type)
    ]


class NoDuplicateEffects:
    """检测同一业务键被提交多次（按业务提交去重口径）。"""

    def __init__(self, effect_type: str | None = None) -> None:
        self.effect_type = effect_type
        self.name = (
            "no_duplicate_effects"
            if effect_type is None
            else f"no_duplicate_effects:{effect_type}"
        )

    def check(self, view: EffectView) -> list[Violation]:
        committed = _committed(view.records, self.effect_type)
        groups: dict[tuple[str, str], list[EffectRecord]] = {}
        for record in committed:
            groups.setdefault((record.effect_type, record.business_key), []).append(record)

        violations: list[Violation] = []
        for (effect_type, business_key), group in groups.items():
            by_idem: dict[str, set[str]] = {}
            for record in group:
                if record.idempotency_key_hash is not None:
                    by_idem.setdefault(record.idempotency_key_hash, set()).add(record.params_hash)

            for idem_hash, hashes in by_idem.items():
                if len(hashes) > 1:
                    effect_ids = tuple(
                        sorted(
                            r.effect_id
                            for r in group
                            if r.idempotency_key_hash == idem_hash
                        )
                    )
                    violations.append(
                        Violation(
                            invariant_name=self.name,
                            message=(
                                f"parameter_mismatch: {effect_type} {business_key} "
                                "has different params for the same idempotency key"
                            ),
                            expected="single params_hash",
                            actual=sorted(hashes),
                            effect_ids=effect_ids,
                        )
                    )

            commit_count = len({commit_identity(r) for r in group})
            if commit_count > 1:
                effect_ids = tuple(sorted(r.effect_id for r in group))
                violations.append(
                    Violation(
                        invariant_name=self.name,
                        message=(
                            f"duplicate_effects: {effect_type} {business_key} "
                            f"committed {commit_count} times"
                        ),
                        expected=1,
                        actual=commit_count,
                        effect_ids=effect_ids,
                    )
                )

        violations.sort(key=lambda v: v.effect_ids)
        return violations


class MaxEffectCount:
    """检测某 effect 类型的业务提交数超过上限。"""

    def __init__(self, effect_type: str, max_count: int) -> None:
        if not effect_type:
            raise ScenarioConfigError("MaxEffectCount.effect_type must be non-empty")
        if max_count < 0:
            raise ScenarioConfigError("MaxEffectCount.max_count must be >= 0")
        self.effect_type = effect_type
        self.max_count = max_count
        self.name = f"max_effect_count:{effect_type}"

    def check(self, view: EffectView) -> list[Violation]:
        actual = view.committed_count(self.effect_type)
        if actual <= self.max_count:
            return []
        effect_ids = tuple(
            sorted(
                r.effect_id
                for r in _committed(view.records, self.effect_type)
            )
        )
        return [
            Violation(
                invariant_name=self.name,
                message=(
                    f"max_effect_count: {self.effect_type} committed {actual} "
                    f"(max {self.max_count})"
                ),
                expected=self.max_count,
                actual=actual,
                effect_ids=effect_ids,
            )
        ]


class ConcurrentCommitDetected:
    """检测同一业务键被「并发」提交（effect 区间重叠）。

    判定基于 `started_tick`/`ended_tick` 区间重叠：两条 COMMITTED 记录同
    (effect_type, business_key)，若区间相交（`a.started < b.ended and b.started < a.ended`）
    即为并发提交。与 `NoDuplicateEffects` 正交：前者判「并发」，后者判「重复」。
    """

    def __init__(self, effect_type: str | None = None) -> None:
        self.effect_type = effect_type
        self.name = (
            "concurrent_commit"
            if effect_type is None
            else f"concurrent_commit:{effect_type}"
        )

    def check(self, view: EffectView) -> list[Violation]:
        committed = _committed(view.records, self.effect_type)
        groups: dict[tuple[str, str], list[EffectRecord]] = {}
        for record in committed:
            groups.setdefault((record.effect_type, record.business_key), []).append(record)

        violations: list[Violation] = []
        for (effect_type, business_key), group in groups.items():
            if _any_overlap(group):
                effect_ids = tuple(sorted(r.effect_id for r in group))
                violations.append(
                    Violation(
                        invariant_name=self.name,
                        message=(
                            f"concurrent_commit: {effect_type} {business_key} "
                            "committed by overlapping (concurrent) effects"
                        ),
                        expected="no overlapping effects",
                        actual="overlapping effects",
                        effect_ids=effect_ids,
                    )
                )

        violations.sort(key=lambda v: v.effect_ids)
        return violations


def _any_overlap(group: list[EffectRecord]) -> bool:
    """组内是否存在区间重叠的任意两条 COMMITTED 记录。

    按 started_tick 排序后检查相邻对（O(n log n)）：两条区间相交当且仅当
    排序序列中存在一对相邻记录相交（经典扫描性质），对每对仍用与双重循环
    完全一致的判定，保证语义不变。
    """
    finite = [r for r in group if r.ended_tick is not None]
    if len(finite) < 2:
        return False
    finite.sort(key=lambda r: r.started_tick)
    for a, b in pairwise(finite):
        if a.started_tick < b.ended_tick and b.started_tick < a.ended_tick:
            return True
    return False


class CustomInvariant:
    """用户自定义断言；predicate 返回 False 或抛异常即违规。"""

    def __init__(
        self,
        name: str,
        predicate: Callable[[EffectView], bool],
        *,
        message: str = "",
    ) -> None:
        if not name:
            raise ScenarioConfigError("CustomInvariant.name must be non-empty")
        self.name = name
        self._predicate = predicate
        self._message = message

    def check(self, view: EffectView) -> list[Violation]:
        try:
            result = self._predicate(view)
        except Exception as exc:
            return [
                Violation(
                    invariant_name=self.name,
                    message=f"{self.name}: predicate raised {type(exc).__name__}: {exc}",
                    expected="no exception",
                    actual=type(exc).__name__,
                    effect_ids=(),
                )
            ]
        if result:
            return []
        return [
            Violation(
                invariant_name=self.name,
                message=self._message or f"{self.name} failed",
                expected=True,
                actual=False,
                effect_ids=(),
            )
        ]
