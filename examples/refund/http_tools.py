"""退款示例：用 HTTP 传输层适配器在真实客户端接缝上注入故障。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from agentreplayguard import Scenario
from agentreplayguard.adapters.httpx import AsyncFaultyTransport, FaultyTransport, HttpEffect

REFUNDS_URL = "https://sim.test/refunds"
HEALTH_URL = "https://sim.test/health"


@dataclass
class RefundService:
    """进程内模拟退款服务，按幂等键去重。"""

    calls: int = 0
    refunds: list[str] = field(default_factory=list)
    _seen: dict[str, dict[str, Any]] = field(default_factory=dict)

    def count(self) -> int:
        return len(self.refunds)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True}, request=request)

        body = json.loads(request.content)
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key is not None and idempotency_key in self._seen:
            return httpx.Response(200, json=self._seen[idempotency_key], request=request)

        self.calls += 1
        self.refunds.append(body["refund_id"])
        payload = {"refund_id": body["refund_id"], "status": "refunded"}
        if idempotency_key is not None:
            self._seen[idempotency_key] = payload
        return httpx.Response(201, json=payload, request=request)


def classify_refund(request: httpx.Request) -> HttpEffect | None:
    """只把 POST /refunds 视为副作用；健康检查等请求透传。"""
    if request.method != "POST" or request.url.path != "/refunds":
        return None
    body = json.loads(request.content)
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


def make_sync_client(scenario: Scenario, service: RefundService) -> httpx.Client:
    transport = FaultyTransport(httpx.MockTransport(service.handle), scenario, classify_refund)
    return httpx.Client(transport=transport)


def make_async_client(scenario: Scenario, service: RefundService) -> httpx.AsyncClient:
    transport = AsyncFaultyTransport(
        httpx.MockTransport(service.handle), scenario, classify_refund
    )
    return httpx.AsyncClient(transport=transport)


def post_refund(
    client: httpx.Client,
    refund_id: str,
    *,
    idempotency_key: str | None = None,
) -> httpx.Response:
    headers = {} if idempotency_key is None else {"Idempotency-Key": idempotency_key}
    return client.post(
        REFUNDS_URL,
        json={"refund_id": refund_id, "amount_cents": 100},
        headers=headers,
    )


async def apost_refund(
    client: httpx.AsyncClient,
    refund_id: str,
    *,
    idempotency_key: str | None = None,
) -> httpx.Response:
    headers = {} if idempotency_key is None else {"Idempotency-Key": idempotency_key}
    return await client.post(
        REFUNDS_URL,
        json={"refund_id": refund_id, "amount_cents": 100},
        headers=headers,
    )
