"""故障模型：五类故障、故障规则、故障计划与确定性注入器。"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .errors import PartialSuccessError, ScenarioConfigError, ServiceError


class FaultKind(str, Enum):
    TIMEOUT_BEFORE_COMMIT = "timeout_before_commit"
    TIMEOUT_AFTER_COMMIT = "timeout_after_commit"
    CONNECTION_RESET = "connection_reset"
    SERVER_ERROR = "server_error"
    PARTIAL_SUCCESS = "partial_success"


_BEFORE_COMMIT = frozenset(
    {
        FaultKind.TIMEOUT_BEFORE_COMMIT,
        FaultKind.CONNECTION_RESET,
        FaultKind.SERVER_ERROR,
    }
)


def is_before_commit(kind: FaultKind) -> bool:
    """该故障是否发生在底层调用提交之前。"""
    return kind in _BEFORE_COMMIT


def fault_exception(kind: FaultKind) -> Exception:
    """把故障类型映射为 guard 应抛出的异常。"""
    if kind is FaultKind.TIMEOUT_BEFORE_COMMIT:
        return TimeoutError("timeout before commit")
    if kind is FaultKind.TIMEOUT_AFTER_COMMIT:
        return TimeoutError("timeout after commit")
    if kind is FaultKind.CONNECTION_RESET:
        return ConnectionResetError("connection reset")
    if kind is FaultKind.SERVER_ERROR:
        return ServiceError(status=500, message="server error")
    if kind is FaultKind.PARTIAL_SUCCESS:
        return PartialSuccessError("partial success")
    raise ScenarioConfigError(f"unknown fault kind: {kind}")


@dataclass(frozen=True)
class FaultRule:
    """一条故障注入规则，按选择器精确匹配一次 guarded 调用。"""

    kind: FaultKind
    effect_type: str | None = None
    business_key: str | None = None
    attempt: int | None = None
    call_index: int | None = None
    times: int = 1
    probability: float = 1.0

    def __post_init__(self) -> None:
        if (
            self.effect_type is None
            and self.business_key is None
            and self.attempt is None
            and self.call_index is None
        ):
            raise ScenarioConfigError("FaultRule requires at least one selector")
        if self.times < 1:
            raise ScenarioConfigError("FaultRule.times must be >= 1")
        if not 0.0 <= self.probability <= 1.0:
            raise ScenarioConfigError("FaultRule.probability must be in [0.0, 1.0]")

    def matches(self, effect_type: str, business_key: str, attempt: int, call_index: int) -> bool:
        return (
            (self.effect_type is None or self.effect_type == effect_type)
            and (self.business_key is None or self.business_key == business_key)
            and (self.attempt is None or self.attempt == attempt)
            and (self.call_index is None or self.call_index == call_index)
        )


class FaultPlan:
    """按声明顺序匹配的故障规则集合。"""

    def __init__(self, rules: Sequence[FaultRule] = ()) -> None:
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[FaultRule, ...]:
        return self._rules

    def __bool__(self) -> bool:
        return bool(self._rules)


@dataclass(frozen=True)
class FaultDirective:
    """注入器对某次调用的判定结果。"""

    kind: FaultKind


class FaultInjector:
    """基于 seed 的确定性故障注入器，按声明顺序匹配规则。"""

    def __init__(self, plan: FaultPlan, seed: int) -> None:
        self._plan = plan
        self._rng = random.Random(seed)
        self._remaining = {index: rule.times for index, rule in enumerate(plan.rules)}
        self._call_index = 0

    def next_directive(self, effect_type: str, business_key: str, attempt: int) -> FaultDirective | None:
        self._call_index += 1
        for index, rule in enumerate(self._plan.rules):
            if self._remaining[index] <= 0:
                continue
            if not rule.matches(effect_type, business_key, attempt, self._call_index):
                continue
            if rule.probability < 1.0 and self._rng.random() >= rule.probability:
                continue
            self._remaining[index] -= 1
            return FaultDirective(rule.kind)
        return None
