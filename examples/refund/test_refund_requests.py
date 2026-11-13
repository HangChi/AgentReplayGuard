"""requests 退款示例：lost-ack 重复副作用检测。"""

from __future__ import annotations

import json

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


class InMemoryRefundService(BaseAdapter):
    """进程内退款服务：模拟服务端提交语义，无真实网络。"""

    def __init__(self) -> None:
        self.commits: list[str] = []

    def send(self, request, **kwargs):
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


def classify(request: requests.PreparedRequest) -> HttpEffect | None:
    if request.method != "POST":
        return None
    body = json.loads(request.body or b"{}")
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


def test_requests_lost_ack_detected():
    scenario = Scenario(
        "refund-requests-lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    base = InMemoryRefundService()
    adapter = RequestsAdapter(base, scenario, classify)
    session = requests.Session()
    session.mount("https://", adapter)

    payload = {"refund_id": "R-REQ-1", "amount_cents": 1000}
    for _ in range(2):
        try:
            session.post("https://sim.test/refunds", json=payload)
        except requests.exceptions.ReadTimeout:
            continue

    report = scenario.finish()
    assert not report.ok
    assert scenario.effects.committed_count("refund") == 2
    assert base.commits == ["R-REQ-1", "R-REQ-1"]
