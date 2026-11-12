"""同步 httpx 传输层适配器：记账、透传、配置校验与故障映射。"""

from __future__ import annotations

import hashlib
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
    NoDuplicateEffects,
    PartialSuccessError,
    Scenario,
    ScenarioConfigError,
    ScenarioStateError,
    ServiceError,
)
from agentreplayguard.adapters.httpx import FaultyTransport, HttpEffect

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
        "http-test",
        seed=0,
        faults=FaultPlan(list(rules)),
        invariants=invariants,
    )


def make_client(
    scenario: Scenario,
    handler: Callable[[httpx.Request], httpx.Response],
    classify: Callable[[httpx.Request], HttpEffect | None] = refund_effect,
) -> httpx.Client:
    transport = FaultyTransport(httpx.MockTransport(handler), scenario, classify)
    return httpx.Client(transport=transport)


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, request=request)


def post_refund(client: httpx.Client, refund_id: str = "R-1", **kwargs: Any) -> httpx.Response:
    payload = {"refund_id": refund_id, "amount_cents": 100}
    return client.post(URL, json=payload, **kwargs)


def test_normal_request_is_recorded_once():
    scenario = make_scenario()
    with make_client(scenario, ok_handler) as client:
        response = post_refund(client)

    assert response.json() == {"ok": True}
    records = scenario.effects.for_key("refund", "R-1")
    assert len(records) == 1
    record = records[0]
    assert record.status is EffectStatus.COMMITTED
    assert record.attempt == 1
    assert record.fault is None
    expected_params_hash = hashlib.sha256(
        json.dumps(
            {"amount_cents": 100}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    assert record.params_hash == expected_params_hash


def test_lost_ack_retry_creates_duplicate():
    scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
        invariants=(NoDuplicateEffects("refund"),),
    )
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True}, request=request)

    with make_client(scenario, handler) as client:
        with pytest.raises(httpx.ReadTimeout):
            post_refund(client)
        assert post_refund(client).status_code == 200

    records = scenario.effects.for_key("refund", "R-1")
    assert [record.status for record in records] == [
        EffectStatus.COMMITTED,
        EffectStatus.COMMITTED,
    ]
    assert [record.attempt for record in records] == [1, 2]
    assert [record.fault for record in records] == [FaultKind.TIMEOUT_AFTER_COMMIT, None]
    assert len(calls) == 2

    report = scenario.finish()
    assert not report.ok


def test_before_commit_fault_skips_base_transport():
    scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund", attempt=1)
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    with make_client(scenario, handler) as client, pytest.raises(httpx.ConnectTimeout):
        post_refund(client)

    assert calls == 0
    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.fault is FaultKind.TIMEOUT_BEFORE_COMMIT


def test_base_exception_is_recorded_and_propagates_unchanged():
    scenario = make_scenario()

    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("boom")

    with make_client(scenario, handler) as client, pytest.raises(RuntimeError, match="boom"):
        post_refund(client)

    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.status is EffectStatus.NOT_COMMITTED
    assert record.error_type == "RuntimeError"
    assert record.error_message == "boom"


def test_close_delegates_to_base_transport():
    class ClosingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.closed = False

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        def close(self) -> None:
            self.closed = True

    base = ClosingTransport()
    transport = FaultyTransport(base, make_scenario(), refund_effect)
    transport.close()
    assert base.closed


def test_finished_scenario_rejects_requests():
    scenario = make_scenario()
    scenario.finish()
    with make_client(scenario, ok_handler) as client, pytest.raises(ScenarioStateError):
        post_refund(client)
    assert scenario.effects.records == ()


# US3：分类、透传与配置校验


def test_unmatched_request_passes_through_without_consuming_fault_plan():
    scenario = make_scenario(
        FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)
    )
    with make_client(scenario, ok_handler) as client:
        assert client.get("https://sim.test/health").status_code == 200
        assert scenario.effects.records == ()

        with pytest.raises(httpx.ReadTimeout):
            post_refund(client)

    assert len(scenario.effects.for_key("refund", "R-1")) == 1


def test_classify_failure_wraps_into_config_error_and_skips_base():
    scenario = make_scenario()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    def bad_classify(request: httpx.Request) -> HttpEffect | None:
        raise ValueError("cannot classify")

    with (
        make_client(scenario, handler, bad_classify) as client,
        pytest.raises(ScenarioConfigError, match="classify failed") as info,
    ):
        post_refund(client)

    assert isinstance(info.value.__cause__, ValueError)
    assert calls == 0
    assert scenario.effects.records == ()


def test_classify_must_return_http_effect_or_none():
    scenario = make_scenario()

    def bad_classify(request: httpx.Request) -> Any:
        return {"effect_type": "refund", "business_key": "R-1"}

    with (
        make_client(scenario, ok_handler, bad_classify) as client,
        pytest.raises(ScenarioConfigError, match="HttpEffect"),
    ):
        post_refund(client)


def test_empty_business_key_fails_fast():
    scenario = make_scenario()

    def bad_classify(request: httpx.Request) -> HttpEffect | None:
        return HttpEffect(effect_type="refund", business_key="", params={})

    with (
        make_client(scenario, ok_handler, bad_classify) as client,
        pytest.raises(ScenarioConfigError, match="business_key"),
    ):
        post_refund(client)

    assert scenario.effects.records == ()


def test_non_serializable_params_fail_before_transport():
    scenario = make_scenario()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    def bad_classify(request: httpx.Request) -> HttpEffect | None:
        return HttpEffect(
            effect_type="refund",
            business_key="R-1",
            params={"bad": object()},
        )

    with (
        make_client(scenario, handler, bad_classify) as client,
        pytest.raises(ScenarioConfigError, match="JSON-serializable"),
    ):
        post_refund(client)

    assert calls == 0
    assert scenario.effects.records == ()


def test_idempotency_key_from_header_is_hashed_and_deduped():
    scenario = make_scenario()
    with make_client(scenario, ok_handler) as client:
        post_refund(client, headers={"Idempotency-Key": "idem-1"})
        post_refund(client, headers={"Idempotency-Key": "idem-1"})

    records = scenario.effects.for_key("refund", "R-1")
    assert len(records) == 2
    expected = hashlib.sha256(b"idem-1").hexdigest()
    assert [record.idempotency_key_hash for record in records] == [expected, expected]
    assert scenario.effects.committed_count("refund") == 1


# US4：五类故障到 httpx 标准异常的映射


@pytest.mark.parametrize(
    ("kind", "expected_type", "status", "cause_type"),
    [
        (
            FaultKind.TIMEOUT_BEFORE_COMMIT,
            httpx.ConnectTimeout,
            EffectStatus.NOT_COMMITTED,
            TimeoutError,
        ),
        (
            FaultKind.TIMEOUT_AFTER_COMMIT,
            httpx.ReadTimeout,
            EffectStatus.COMMITTED,
            TimeoutError,
        ),
        (
            FaultKind.CONNECTION_RESET,
            httpx.ConnectError,
            EffectStatus.NOT_COMMITTED,
            ConnectionResetError,
        ),
        (
            FaultKind.SERVER_ERROR,
            httpx.HTTPStatusError,
            EffectStatus.NOT_COMMITTED,
            ServiceError,
        ),
        (
            FaultKind.PARTIAL_SUCCESS,
            httpx.ReadError,
            EffectStatus.COMMITTED,
            PartialSuccessError,
        ),
    ],
)
def test_fault_mapping(kind, expected_type, status, cause_type):
    scenario = make_scenario(FaultRule(kind, effect_type="refund", attempt=1))
    with make_client(scenario, ok_handler) as client, pytest.raises(expected_type) as info:
        post_refund(client)

    error = info.value
    assert error.request.url == httpx.URL(URL)
    assert isinstance(error.__cause__, cause_type)
    if kind is FaultKind.SERVER_ERROR:
        assert error.response.status_code == 500

    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.status is status
    assert record.fault is kind


def test_base_timeout_is_not_rewritten_as_httpx_exception():
    scenario = make_scenario()

    def handler(request: httpx.Request) -> httpx.Response:
        raise TimeoutError("socket timeout")

    with make_client(scenario, handler) as client, pytest.raises(TimeoutError) as info:
        post_refund(client)

    assert type(info.value) is TimeoutError
    assert not isinstance(info.value, httpx.HTTPError)
    record = scenario.effects.for_key("refund", "R-1")[0]
    assert record.fault is None
