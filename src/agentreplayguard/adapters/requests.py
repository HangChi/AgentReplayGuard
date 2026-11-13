"""requests 适配器：把 HTTP 请求接入 EffectGuard 的记账与故障注入。

requests 是可选依赖：只有显式导入本模块时才要求安装，核心包不受影响。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import requests
    from requests.adapters import BaseAdapter
except ImportError as exc:  # pragma: no cover - 仅在未安装可选依赖时触发
    raise ImportError(
        "agentreplayguard.adapters.requests requires the optional dependency "
        "'requests'. Install it with: pip install agentreplayguard[requests]"
    ) from exc

from ..effects import EffectRecord
from ..faults import FaultKind
from ..scenario import Scenario
from ._http_common import HttpEffect, classify_or_raise

__all__ = ["HttpEffect", "RequestsAdapter"]

ClassifyRequest = Callable[[requests.PreparedRequest], "HttpEffect | None"]


def _map_injected_fault(
    record: EffectRecord | None,
    request: requests.PreparedRequest,
) -> Exception | None:
    """把 guard 注入的故障转换为 requests 标准异常；非注入异常返回 None。"""
    if record is None or record.fault is None:
        return None

    kind = record.fault
    if kind is FaultKind.TIMEOUT_BEFORE_COMMIT:
        return requests.exceptions.ConnectTimeout("timeout before commit", request=request)
    if kind is FaultKind.TIMEOUT_AFTER_COMMIT:
        return requests.exceptions.ReadTimeout("timeout after commit", request=request)
    if kind is FaultKind.CONNECTION_RESET:
        return requests.exceptions.ConnectionError("connection reset", request=request)
    if kind is FaultKind.SERVER_ERROR:
        resp = requests.Response()
        resp.status_code = 500
        resp.request = request
        resp.url = request.url or ""
        return requests.exceptions.HTTPError("server error", response=resp)
    if kind is FaultKind.PARTIAL_SUCCESS:
        return requests.exceptions.ChunkedEncodingError("partial success", request=request)
    return None


def _new_record(scenario: Scenario, records_before: int) -> EffectRecord | None:
    records = scenario.effects.records
    if len(records) <= records_before:
        return None
    return records[records_before]


class RequestsAdapter(BaseAdapter):
    """包裹同步 requests 请求，为已分类请求记账并注入确定性故障。"""

    def __init__(
        self,
        base: BaseAdapter,
        scenario: Scenario,
        classify: ClassifyRequest,
    ) -> None:
        self._base = base
        self._scenario = scenario
        self._classify = classify

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: Any = True,
        cert: Any = None,
        proxies: Any = None,
    ) -> requests.Response:
        effect = classify_or_raise(self._classify, request)
        if effect is None:
            return self._base.send(
                request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies
            )

        records_before = len(self._scenario.effects.records)
        try:
            return self._scenario.guard().call(
                effect.effect_type,
                self._base.send,
                request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
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
