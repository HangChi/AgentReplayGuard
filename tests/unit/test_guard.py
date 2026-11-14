from __future__ import annotations

import hashlib
import json

import pytest

from agentreplayguard import (
    EffectStatus,
    FaultKind,
    FaultPlan,
    FaultRule,
    Scenario,
    ScenarioConfigError,
)


def _sha256_params(obj: dict) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_key_from_param_name():
    scenario = Scenario("s")
    guard = scenario.guard()

    def fn(refund_id):
        return "ok"

    assert guard.call("refund", fn, refund_id="R-1", key="refund_id") == "ok"
    record = scenario.effects.records[0]
    assert record.business_key == "R-1"
    assert record.status is EffectStatus.COMMITTED


def test_key_missing_raises_config_error():
    scenario = Scenario("s")
    guard = scenario.guard()

    def fn(amount):
        return amount

    with pytest.raises(ScenarioConfigError):
        guard.call("refund", fn, amount=5, key="refund_id")


def test_params_exclude_key_and_idempotency():
    scenario = Scenario("s")
    guard = scenario.guard()

    def fn(refund_id, amount, idempotency_key):
        return refund_id

    # fn 的幂等键值通过位置参数传入，避免与 guard 的同名配置参数冲突
    guard.call(
        "refund",
        fn,
        "R-1",
        5,
        "k1",
        key="refund_id",
        idempotency_key="idempotency_key",
    )
    record = scenario.effects.records[0]
    assert record.params_hash == _sha256_params({"amount": 5})
    assert record.idempotency_key_hash is not None


def test_attempt_increments():
    scenario = Scenario("s")
    guard = scenario.guard()

    def fn(refund_id):
        return refund_id

    guard.call("refund", fn, refund_id="R-1", key="refund_id")
    guard.call("refund", fn, refund_id="R-1", key="refund_id")
    assert scenario.effects.attempts("refund", "R-1") == 2
    assert [r.attempt for r in scenario.effects.records] == [1, 2]


def test_before_commit_fault_not_committed():
    scenario = Scenario(
        "s",
        faults=FaultPlan([FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund")]),
    )
    guard = scenario.guard()
    called = []

    def fn(refund_id):
        called.append(refund_id)
        return "ok"

    with pytest.raises(TimeoutError):
        guard.call("refund", fn, refund_id="R-1", key="refund_id")
    assert called == []
    record = scenario.effects.records[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "TimeoutError"


def test_after_commit_fault_committed_with_error():
    scenario = Scenario(
        "s",
        faults=FaultPlan([FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund")]),
    )
    guard = scenario.guard()

    def fn(refund_id):
        return "ok"

    with pytest.raises(TimeoutError):
        guard.call("refund", fn, refund_id="R-1", key="refund_id")
    record = scenario.effects.records[0]
    assert record.status is EffectStatus.COMMITTED
    assert record.error_type == "TimeoutError"


def test_fn_exception_passthrough_not_committed():
    scenario = Scenario("s")
    guard = scenario.guard()

    def fn(refund_id):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        guard.call("refund", fn, refund_id="R-1", key="refund_id")
    record = scenario.effects.records[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "ValueError"
    assert record.error_message == "boom"


def test_effect_decorator_preserves_signature():
    scenario = Scenario("s")

    @scenario.guard().effect("refund", key="refund_id")
    def refund(refund_id):
        """Refund docstring."""
        return refund_id

    assert refund.__name__ == "refund"
    assert refund.__doc__ == "Refund docstring."
    assert refund("R-9") == "R-9"


def test_fn_exception_carries_attempt_note():
    """异常上应附带 attempt 上下文 note，便于排障。"""
    scenario = Scenario("s")
    guard = scenario.guard()

    def fn(refund_id):
        raise ValueError("boom")

    with pytest.raises(ValueError) as excinfo:
        guard.call("refund", fn, refund_id="R-1", key="refund_id")

    notes = getattr(excinfo.value, "__notes__", None)
    if notes is not None:  # Python 3.11+
        assert any("effect=refund" in n and "key='R-1'" in n and "attempt=1" in n for n in notes)


def test_fault_exception_carries_attempt_note():
    """故障注入异常也应附带 attempt 上下文 note。"""
    scenario = Scenario(
        "s",
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
    )
    guard = scenario.guard()

    def fn(refund_id):
        return "ok"

    with pytest.raises(TimeoutError) as excinfo:
        guard.call("refund", fn, refund_id="R-1", key="refund_id")

    notes = getattr(excinfo.value, "__notes__", None)
    if notes is not None:  # Python 3.11+
        assert any("effect=refund" in n and "attempt=1" in n for n in notes)
