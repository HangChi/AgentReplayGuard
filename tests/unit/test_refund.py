from __future__ import annotations

import pytest

from agentreplayguard.services.refund import IdempotencyConflict, SimulatedRefundService


def test_no_key_adds_each_time():
    service = SimulatedRefundService()
    service.refund("R-1", 100)
    service.refund("R-1", 100)
    assert service.count() == 2


def test_same_key_same_params_returns_existing():
    service = SimulatedRefundService()
    first = service.refund("R-1", 100, idempotency_key="k1")
    second = service.refund("R-1", 100, idempotency_key="k1")
    assert first is second
    assert service.count() == 1


def test_same_key_diff_params_conflict():
    service = SimulatedRefundService()
    service.refund("R-1", 100, idempotency_key="k1")
    with pytest.raises(IdempotencyConflict):
        service.refund("R-1", 200, idempotency_key="k1")


def test_queries():
    service = SimulatedRefundService()
    refund = service.refund("R-1", 100, idempotency_key="k1")
    assert service.by_refund_id("R-1") is refund
    assert service.by_idempotency_key("k1") is refund
    assert service.by_refund_id("missing") is None
