"""RequestsAdapter 单元测试：记账、故障映射、异常传播。"""

from __future__ import annotations

import pytest
import requests
from requests.adapters import BaseAdapter

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    Scenario,
    ScenarioConfigError,
)
from agentreplayguard.adapters.requests import HttpEffect, RequestsAdapter


class MockAdapter(BaseAdapter):
    """内存 mock adapter：返回预设 Response，无真实 socket。"""

    def __init__(self, *, status: int = 200, body: bytes = b"{}") -> None:
        self._status = status
        self._body = body
        self.calls: list[requests.PreparedRequest] = []

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        self.calls.append(request)
        resp = requests.Response()
        resp.status_code = self._status
        resp._content = self._body
        resp.headers["Content-Type"] = "application/json"
        resp.request = request
        resp.url = request.url
        return resp

    def close(self):
        self.closed = True


def _make_request(method="POST", url="https://sim.test/refunds", json_body=None):
    req = requests.Request(method, url, json=json_body or {"refund_id": "R-1"})
    return req.prepare()


def _session_with(scenario, classify, base=None):
    base = base or MockAdapter()
    adapter = RequestsAdapter(base, scenario, classify)
    session = requests.Session()
    session.mount("https://", adapter)
    return session, base, adapter


def _refund_effect(r):
    return HttpEffect("refund", "R-1", {"amount": 100})


def test_classified_request_records_committed():
    sc = Scenario("s", seed=0)
    session, base, _ = _session_with(sc, _refund_effect)
    session.post("https://sim.test/refunds", json={"refund_id": "R-1"})

    assert len(sc.effects.records) == 1
    assert sc.effects.records[0].status.value == "committed"
    assert sc.effects.records[0].business_key == "R-1"
    assert len(base.calls) == 1


def test_unclassified_request_passthrough():
    sc = Scenario("s", seed=0)
    session, base, _ = _session_with(sc, lambda r: None)
    session.get("https://sim.test/health")

    assert len(sc.effects.records) == 0
    assert len(base.calls) == 1


def test_classify_exception_wrapped():
    sc = Scenario("s", seed=0)

    def bad(r):
        raise ValueError("boom")

    session, base, _ = _session_with(sc, bad)
    with pytest.raises(ScenarioConfigError):
        session.post("https://sim.test/refunds", json={})
    assert len(base.calls) == 0


def test_timeout_before_commit_raises_connect_timeout():
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund", attempt=1)]
        ),
    )
    session, base, _ = _session_with(sc, _refund_effect)
    with pytest.raises(requests.exceptions.ConnectTimeout):
        session.post("https://sim.test/refunds", json={})
    assert len(base.calls) == 0  # 提交前故障不调用底层
    assert sc.effects.records[0].status.value == "not_committed"


def test_timeout_after_commit_raises_read_timeout():
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
    )
    session, _base, _ = _session_with(sc, _refund_effect)
    with pytest.raises(requests.exceptions.ReadTimeout):
        session.post("https://sim.test/refunds", json={})
    assert sc.effects.records[0].status.value == "committed"


def test_connection_reset_raises_connection_error():
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.CONNECTION_RESET, effect_type="refund", attempt=1)]),
    )
    session, base, _ = _session_with(sc, _refund_effect)
    with pytest.raises(requests.exceptions.ConnectionError):
        session.post("https://sim.test/refunds", json={})
    assert len(base.calls) == 0


def test_server_error_raises_http_error():
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.SERVER_ERROR, effect_type="refund", attempt=1)]),
    )
    session, base, _ = _session_with(sc, _refund_effect)
    with pytest.raises(requests.exceptions.HTTPError):
        session.post("https://sim.test/refunds", json={})
    assert len(base.calls) == 0


def test_partial_success_raises_chunked_encoding_error():
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.PARTIAL_SUCCESS, effect_type="refund", attempt=1)]),
    )
    session, _base, _ = _session_with(sc, _refund_effect)
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        session.post("https://sim.test/refunds", json={})


def test_stream_body_loss_stream_read_raises_and_records_committed():
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.STREAM_BODY_LOSS, effect_type="refund", attempt=1)]),
    )
    session, base, _ = _session_with(sc, _refund_effect)

    # 流式：响应头正常返回，读 body 时抛 ChunkedEncodingError
    resp = session.post("https://sim.test/refunds", json={}, stream=True)
    assert resp.status_code == 200
    assert len(base.calls) == 1
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        _ = resp.content  # 触发读取，抛 ChunkedEncodingError

    record = sc.effects.records[0]
    assert record.status.value == "committed"
    assert record.fault is FaultKind.STREAM_BODY_LOSS


def test_stream_body_loss_non_stream_read_also_raises():
    """非流式 send 内部读 body，也会抛 ChunkedEncodingError，语义仍成立。"""
    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.STREAM_BODY_LOSS, effect_type="refund", attempt=1)]),
    )
    session, _base, _ = _session_with(sc, _refund_effect)
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        session.post("https://sim.test/refunds", json={})

    record = sc.effects.records[0]
    assert record.status.value == "committed"
    assert record.fault is FaultKind.STREAM_BODY_LOSS


def test_stream_body_loss_idempotency_folds():
    from agentreplayguard import NoDuplicateEffects

    def refund_effect_with_ik(r):
        return HttpEffect("refund", "R-1", {"amount": 100}, idempotency_key="ik-1")

    sc = Scenario(
        "s",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.STREAM_BODY_LOSS, effect_type="refund", attempt=1)]),
        invariants=[NoDuplicateEffects("refund")],
    )
    session, _base, _ = _session_with(sc, refund_effect_with_ik)

    for _ in range(2):
        try:
            session.post("https://sim.test/refunds", json={})
        except requests.exceptions.ChunkedEncodingError:
            continue

    report = sc.finish()
    assert report.ok  # 幂等键折叠为一次提交
    assert sc.effects.committed_count("refund") == 1


def test_base_exception_propagates_and_records_not_committed():
    sc = Scenario("s", seed=0)

    class BoomAdapter(MockAdapter):
        def send(self, request, **kwargs):
            self.calls.append(request)
            raise requests.exceptions.ProxyError("proxy down")

    session, _base, _ = _session_with(sc, _refund_effect, base=BoomAdapter())
    with pytest.raises(requests.exceptions.ProxyError):
        session.post("https://sim.test/refunds", json={})

    assert sc.effects.records[0].status.value == "not_committed"
    assert sc.effects.records[0].fault is None


def test_close_delegates_to_base():
    sc = Scenario("s", seed=0)
    base = MockAdapter()
    adapter = RequestsAdapter(base, sc, _refund_effect)
    adapter.close()
    assert base.closed is True
