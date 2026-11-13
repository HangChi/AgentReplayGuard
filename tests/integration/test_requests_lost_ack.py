"""requests lost-ack 重复副作用检测集成测试。"""

from __future__ import annotations

import requests
from requests.adapters import BaseAdapter

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.requests import HttpEffect, RequestsAdapter


class RefundService(BaseAdapter):
    """内存退款服务：模拟真实服务端提交语义。"""

    def __init__(self) -> None:
        self.commits: list[str] = []

    def send(self, request, **kwargs):
        # 解析 refund_id，模拟「服务端提交」
        import json

        body = json.loads(request.body or b"{}")
        self.commits.append(body["refund_id"])
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"ok": true}'
        resp.headers["Content-Type"] = "application/json"
        resp.request = request
        resp.url = request.url
        return resp

    def close(self):
        pass


def _classify(request: requests.PreparedRequest) -> HttpEffect | None:
    import json

    if request.method != "POST":
        return None
    body = json.loads(request.body or b"{}")
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount": body["amount"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


def _make_scenario(idempotent: bool) -> Scenario:
    return Scenario(
        "requests-lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )


def _post_with_retry(session, refund_id, amount, idempotency_key=None):
    """业务侧重试逻辑：捕获 ReadTimeout 后重试一次。"""
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    payload = {"refund_id": refund_id, "amount": amount}
    for _ in range(2):
        try:
            return session.post("https://sim.test/refunds", json=payload, headers=headers)
        except requests.exceptions.ReadTimeout:
            continue
    return None


def test_lost_ack_without_idempotency_detected():
    scenario = _make_scenario(idempotent=False)
    base = RefundService()
    adapter = RequestsAdapter(base, scenario, _classify)
    session = requests.Session()
    session.mount("https://", adapter)

    _post_with_retry(session, "R-1", 100)

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    # 服务端真实提交了两次
    assert base.commits == ["R-1", "R-1"]


def test_lost_ack_with_idempotency_folded():
    scenario = _make_scenario(idempotent=True)
    base = RefundService()
    adapter = RequestsAdapter(base, scenario, _classify)
    session = requests.Session()
    session.mount("https://", adapter)

    _post_with_retry(session, "R-2", 100, idempotency_key="ik-R-2")

    report = scenario.finish()
    assert report.ok
    assert scenario.effects.committed_count("refund") == 1
