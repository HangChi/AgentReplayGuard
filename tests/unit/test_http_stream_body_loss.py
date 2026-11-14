"""流式响应体丢失（STREAM_BODY_LOSS）故障注入测试。"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.httpx import (
    AsyncFaultyTransport,
    FaultyTransport,
    HttpEffect,
)

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


def make_scenario(*rules: FaultRule, invariants: tuple[Any, ...] = ()) -> Scenario:
    return Scenario(
        "stream-loss",
        seed=0,
        faults=FaultPlan(list(rules)),
        invariants=invariants,
    )


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, request=request)


def stream_loss_rule(**kwargs: Any) -> FaultRule:
    return FaultRule(FaultKind.STREAM_BODY_LOSS, effect_type="refund", attempt=1, **kwargs)


def test_stream_body_loss_kind_is_after_commit():
    assert FaultKind.STREAM_BODY_LOSS.value == "stream_body_loss"
    from agentreplayguard.faults import is_before_commit

    assert not is_before_commit(FaultKind.STREAM_BODY_LOSS)


def test_stream_body_loss_stream_read_raises_and_records_committed():
    scenario = make_scenario(stream_loss_rule())
    transport = FaultyTransport(httpx.MockTransport(ok_handler), scenario, refund_effect)
    client = httpx.Client(transport=transport)

    payload = {"refund_id": "R-1", "amount_cents": 100}
    # 流式：响应头正常返回，读 body 时抛 ReadError
    with client.stream("POST", URL, json=payload) as resp:
        assert resp.status_code == 200  # 响应头正常
        with pytest.raises(httpx.ReadError):
            resp.read()

    record = scenario.effects.records[0]
    assert record.status.value == "committed"
    assert record.fault is FaultKind.STREAM_BODY_LOSS


def test_stream_body_loss_non_stream_read_also_raises():
    """非流式 send 内部读 body，也会抛 ReadError，语义仍成立。"""
    scenario = make_scenario(stream_loss_rule())
    transport = FaultyTransport(httpx.MockTransport(ok_handler), scenario, refund_effect)
    client = httpx.Client(transport=transport)

    payload = {"refund_id": "R-1", "amount_cents": 100}
    with pytest.raises(httpx.ReadError):
        client.post(URL, json=payload)

    record = scenario.effects.records[0]
    assert record.status.value == "committed"
    assert record.fault is FaultKind.STREAM_BODY_LOSS


def test_stream_body_loss_unclassified_passthrough():
    scenario = make_scenario(stream_loss_rule())
    transport = FaultyTransport(httpx.MockTransport(ok_handler), scenario, lambda r: None)
    client = httpx.Client(transport=transport)

    resp = client.get("https://sim.test/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert len(scenario.effects.records) == 0


def test_stream_body_loss_retry_detects_duplicate():
    scenario = make_scenario(stream_loss_rule(), invariants=[NoDuplicateEffects("refund")])
    transport = FaultyTransport(httpx.MockTransport(ok_handler), scenario, refund_effect)
    client = httpx.Client(transport=transport)

    payload = {"refund_id": "R-1", "amount_cents": 100}
    # 业务侧重试：读 body 失败后重试
    for _ in range(2):
        try:
            client.post(URL, json=payload)
        except httpx.ReadError:
            continue

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2


def test_stream_body_loss_idempotency_folds():
    scenario = make_scenario(stream_loss_rule(), invariants=[NoDuplicateEffects("refund")])
    transport = FaultyTransport(httpx.MockTransport(ok_handler), scenario, refund_effect)
    client = httpx.Client(transport=transport)

    payload = {"refund_id": "R-1", "amount_cents": 100}
    headers = {"Idempotency-Key": "ik-1"}
    for _ in range(2):
        try:
            client.post(URL, json=payload, headers=headers)
        except httpx.ReadError:
            continue

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1


def test_async_stream_body_loss():
    import asyncio

    scenario = make_scenario(stream_loss_rule())
    transport = AsyncFaultyTransport(httpx.MockTransport(ok_handler), scenario, refund_effect)
    client = httpx.AsyncClient(transport=transport)

    async def run():
        payload = {"refund_id": "R-1", "amount_cents": 100}
        with pytest.raises(httpx.ReadError):
            await client.post(URL, json=payload)

    asyncio.run(run())

    record = scenario.effects.records[0]
    assert record.status.value == "committed"
    assert record.fault is FaultKind.STREAM_BODY_LOSS
