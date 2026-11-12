"""异步 httpx 传输层适配器：记账、取消、关闭委托与同步等价。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from agentreplayguard import (
    EffectStatus,
    FaultKind,
    FaultPlan,
    FaultRule,
    Scenario,
    ScenarioConfigError,
)
from agentreplayguard.adapters.httpx import AsyncFaultyTransport, HttpEffect

URL = "https://sim.test/refunds"


def refund_effect(request: httpx.Request) -> HttpEffect | None:
    if request.method != "POST":
        return None
    body = json.loads(request.content or b"{}")
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


def make_scenario(*rules: FaultRule) -> Scenario:
    return Scenario("http-async-test", seed=0, faults=FaultPlan(list(rules)))


def make_transport(
    scenario: Scenario,
    handler: Callable[[httpx.Request], Any],
    classify: Callable[[httpx.Request], HttpEffect | None] = refund_effect,
) -> AsyncFaultyTransport:
    return AsyncFaultyTransport(httpx.MockTransport(handler), scenario, classify)


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, request=request)


async def post_refund(client: httpx.AsyncClient, **kwargs: Any) -> httpx.Response:
    payload = {"refund_id": "R-1", "amount_cents": 100}
    return await client.post(URL, json=payload, **kwargs)


def records_signature(scenario: Scenario) -> list[tuple[Any, ...]]:
    return [
        (r.effect_type, r.business_key, r.attempt, r.status, r.fault)
        for r in scenario.effects.records
    ]


def test_async_normal_request_is_recorded_once():
    scenario = make_scenario()

    async def main() -> None:
        async with httpx.AsyncClient(transport=make_transport(scenario, ok_handler)) as client:
            response = await post_refund(client)
        assert response.json() == {"ok": True}

    asyncio.run(main())

    records = scenario.effects.for_key("refund", "R-1")
    assert len(records) == 1
    assert records[0].status is EffectStatus.COMMITTED
    assert records[0].attempt == 1


def test_async_lost_ack_retry_creates_duplicate():
    scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True}, request=request)

    async def main() -> None:
        async with httpx.AsyncClient(transport=make_transport(scenario, handler)) as client:
            with pytest.raises(httpx.ReadTimeout):
                await post_refund(client)
            assert (await post_refund(client)).status_code == 200

    asyncio.run(main())

    records = scenario.effects.for_key("refund", "R-1")
    assert [record.status for record in records] == [
        EffectStatus.COMMITTED,
        EffectStatus.COMMITTED,
    ]
    assert [record.attempt for record in records] == [1, 2]
    assert calls == 2


def test_async_before_commit_fault_skips_base_transport():
    scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund", attempt=1)
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    async def main() -> None:
        async with httpx.AsyncClient(transport=make_transport(scenario, handler)) as client:
            with pytest.raises(httpx.ConnectTimeout):
                await post_refund(client)

    asyncio.run(main())

    assert calls == 0
    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.fault is FaultKind.TIMEOUT_BEFORE_COMMIT


def test_async_base_exception_is_recorded_and_propagates():
    scenario = make_scenario()

    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("boom")

    async def main() -> None:
        async with httpx.AsyncClient(transport=make_transport(scenario, handler)) as client:
            with pytest.raises(RuntimeError, match="boom"):
                await post_refund(client)

    asyncio.run(main())

    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "RuntimeError"


def test_async_cancellation_records_unknown():
    scenario = make_scenario()

    async def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async def main() -> None:
        async with httpx.AsyncClient(transport=make_transport(scenario, handler)) as client:
            with pytest.raises(asyncio.CancelledError):
                await post_refund(client)

    asyncio.run(main())

    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.status is EffectStatus.UNKNOWN
    assert record.error_type == "CancelledError"


def test_async_unmatched_request_passes_through():
    scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)
    )

    async def main() -> None:
        async with httpx.AsyncClient(transport=make_transport(scenario, ok_handler)) as client:
            response = await client.get("https://sim.test/health")
            assert response.status_code == 200
            with pytest.raises(httpx.ReadTimeout):
                await post_refund(client)

    asyncio.run(main())

    assert len(scenario.effects.records) == 1


def test_async_classify_error_is_config_error():
    scenario = make_scenario()

    def bad_classify(request: httpx.Request) -> HttpEffect | None:
        raise ValueError("cannot classify")

    async def main() -> None:
        async with httpx.AsyncClient(
            transport=make_transport(scenario, ok_handler, bad_classify)
        ) as client:
            with pytest.raises(ScenarioConfigError, match="classify failed"):
                await post_refund(client)

    asyncio.run(main())
    assert scenario.effects.records == ()


def test_aclose_delegates_to_base_transport():
    class ClosingTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.closed = False

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        async def aclose(self) -> None:
            self.closed = True

    base = ClosingTransport()
    transport = AsyncFaultyTransport(base, make_scenario(), refund_effect)

    async def main() -> None:
        await transport.aclose()

    asyncio.run(main())
    assert base.closed


def test_sync_and_async_lost_ack_are_equivalent():
    from agentreplayguard.adapters.httpx import FaultyTransport

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    sync_scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)
    )
    sync_transport = FaultyTransport(httpx.MockTransport(handler), sync_scenario, refund_effect)
    with httpx.Client(transport=sync_transport) as sync_client:
        with pytest.raises(httpx.ReadTimeout):
            sync_client.post(URL, json={"refund_id": "R-1", "amount_cents": 100})
        sync_client.post(URL, json={"refund_id": "R-1", "amount_cents": 100})

    async_scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)
    )

    async def main() -> None:
        async with httpx.AsyncClient(
            transport=make_transport(async_scenario, handler)
        ) as async_client:
            with pytest.raises(httpx.ReadTimeout):
                await post_refund(async_client)
            await post_refund(async_client)

    asyncio.run(main())

    assert records_signature(sync_scenario) == records_signature(async_scenario)
