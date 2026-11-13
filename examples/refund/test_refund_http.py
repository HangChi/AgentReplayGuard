"""HTTP 传输层示例验收：同步/异步 lost-ack 与幂等键。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from agentreplayguard import (
    EffectStatus,
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)

from .http_tools import (
    RefundService,
    apost_refund,
    make_async_client,
    make_sync_client,
    post_refund,
)


def lost_ack_scenario() -> Scenario:
    return Scenario(
        "http-refund-lost-ack",
        seed=7,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )


def test_sync_lost_ack_detects_duplicate():
    scenario = lost_ack_scenario()
    service = RefundService()

    with make_sync_client(scenario, service) as client:
        with pytest.raises(httpx.ReadTimeout):
            post_refund(client, "R-1")
        response = post_refund(client, "R-1")

    assert response.status_code == 201
    assert service.count() == 2

    report = scenario.finish()
    assert not report.ok
    committed = [
        record
        for record in report.effects
        if record.effect_type == "refund" and record.status is EffectStatus.COMMITTED
    ]
    assert len(committed) == 2
    assert [record.attempt for record in committed] == [1, 2]


def test_async_lost_ack_detects_duplicate():
    scenario = lost_ack_scenario()
    service = RefundService()

    async def main() -> None:
        async with make_async_client(scenario, service) as client:
            with pytest.raises(httpx.ReadTimeout):
                await apost_refund(client, "R-1")
            response = await apost_refund(client, "R-1")
        assert response.status_code == 201

    asyncio.run(main())
    assert service.count() == 2

    report = scenario.finish()
    assert not report.ok
    assert len(report.effects) == 2


def test_idempotency_key_prevents_duplicate():
    scenario = lost_ack_scenario()
    service = RefundService()

    with make_sync_client(scenario, service) as client:
        with pytest.raises(httpx.ReadTimeout):
            post_refund(client, "R-1", idempotency_key="idem-1")
        response = post_refund(client, "R-1", idempotency_key="idem-1")

    assert response.status_code == 200
    assert service.count() == 1
    assert scenario.effects.committed_count("refund") == 1
    assert scenario.finish().ok


def test_read_only_request_is_not_recorded():
    scenario = lost_ack_scenario()
    service = RefundService()

    with make_sync_client(scenario, service) as client:
        assert client.get("https://sim.test/health").status_code == 200

    assert scenario.effects.records == ()
