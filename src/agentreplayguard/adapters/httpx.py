"""httpx 传输层适配器：把 HTTP 请求接入 EffectGuard 的记账与故障注入。

httpx 是可选依赖：只有显式导入本模块时才要求安装，核心包不受影响。
"""

from __future__ import annotations

from collections.abc import Callable

try:
    import httpx
except ImportError as exc:  # pragma: no cover - 仅在未安装可选依赖时触发
    raise ImportError(
        "agentreplayguard.adapters.httpx requires the optional dependency 'httpx'. "
        "Install it with: pip install agentreplayguard[httpx]"
    ) from exc

from ..effects import EffectRecord
from ..faults import FaultKind
from ..scenario import Scenario
from ._http_common import HttpEffect, classify_or_raise

__all__ = ["AsyncFaultyTransport", "FaultyTransport", "HttpEffect"]

ClassifyRequest = Callable[[httpx.Request], "HttpEffect | None"]


def _classify_or_raise(
    classify: ClassifyRequest,
    request: httpx.Request,
) -> HttpEffect | None:
    return classify_or_raise(classify, request)


def _map_injected_fault(
    record: EffectRecord | None,
    request: httpx.Request,
) -> Exception | None:
    """把 guard 注入的故障转换为 httpx 标准异常；非注入异常返回 None。"""
    if record is None or record.fault is None:
        return None

    kind = record.fault
    if kind is FaultKind.TIMEOUT_BEFORE_COMMIT:
        return httpx.ConnectTimeout("timeout before commit", request=request)
    if kind is FaultKind.TIMEOUT_AFTER_COMMIT:
        return httpx.ReadTimeout("timeout after commit", request=request)
    if kind is FaultKind.CONNECTION_RESET:
        return httpx.ConnectError("connection reset", request=request)
    if kind is FaultKind.SERVER_ERROR:
        return httpx.HTTPStatusError(
            "server error",
            request=request,
            response=httpx.Response(500, request=request),
        )
    if kind is FaultKind.PARTIAL_SUCCESS:
        return httpx.ReadError("partial success", request=request)
    return None


def _new_record(scenario: Scenario, records_before: int) -> EffectRecord | None:
    records = scenario.effects.records
    if len(records) <= records_before:
        return None
    return records[records_before]


class FaultyTransport(httpx.BaseTransport):
    """包裹同步 transport，为已分类请求记账并注入确定性故障。"""

    def __init__(
        self,
        base: httpx.BaseTransport,
        scenario: Scenario,
        classify: ClassifyRequest,
    ) -> None:
        self._base = base
        self._scenario = scenario
        self._classify = classify

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        effect = _classify_or_raise(self._classify, request)
        if effect is None:
            return self._base.handle_request(request)

        records_before = len(self._scenario.effects.records)
        try:
            return self._scenario.guard().call(
                effect.effect_type,
                self._base.handle_request,
                request,
                key=lambda _args: effect.business_key,
                params=lambda _args: effect.params,
                idempotency_key=lambda _args: effect.idempotency_key,
            )
        except Exception as exc:
            mapped = _map_injected_fault(
                _new_record(self._scenario, records_before), request
            )
            if mapped is None:
                raise
            raise mapped from exc

    def close(self) -> None:
        self._base.close()


class AsyncFaultyTransport(httpx.AsyncBaseTransport):
    """包裹异步 transport，语义与同步版一致。"""

    def __init__(
        self,
        base: httpx.AsyncBaseTransport,
        scenario: Scenario,
        classify: ClassifyRequest,
    ) -> None:
        self._base = base
        self._scenario = scenario
        self._classify = classify

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        effect = _classify_or_raise(self._classify, request)
        if effect is None:
            return await self._base.handle_async_request(request)

        records_before = len(self._scenario.effects.records)
        try:
            return await self._scenario.guard().acall(
                effect.effect_type,
                self._base.handle_async_request,
                request,
                key=lambda _args: effect.business_key,
                params=lambda _args: effect.params,
                idempotency_key=lambda _args: effect.idempotency_key,
            )
        except Exception as exc:
            mapped = _map_injected_fault(
                _new_record(self._scenario, records_before), request
            )
            if mapped is None:
                raise
            raise mapped from exc

    async def aclose(self) -> None:
        await self._base.aclose()
