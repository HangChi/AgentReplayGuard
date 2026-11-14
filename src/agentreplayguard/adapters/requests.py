"""requests 适配器：把 HTTP 请求接入 EffectGuard 的记账与故障注入。

requests 是可选依赖：只有显式导入本模块时才要求安装，核心包不受影响。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
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


class _BrokenBodyStream:
    """模拟「响应头到达、body 丢失」：读 body 时抛 ChunkedEncodingError。

    语义与 httpx 适配器的 `_BrokenSyncBodyStream` 一致：请求已提交（status=committed），
    响应头正常返回，但读取响应体时失败。
    """

    def __init__(self, body: bytes) -> None:
        self._body = body

    def stream(self, amt: int | None, decode_content: bool = False) -> Iterator[bytes]:
        # 先产出已到达的部分内容（模拟部分 body 已收到），随后抛错
        if self._body:
            yield self._body
        raise requests.exceptions.ChunkedEncodingError("stream body lost after headers")

    def read(self, amt: int | None = None) -> bytes:
        raise requests.exceptions.ChunkedEncodingError("stream body lost after headers")


def _wrap_stream_body_loss(
    response: requests.Response,
    request: requests.PreparedRequest,
) -> requests.Response:
    """复制响应头，替换 body 为读取时抛 ChunkedEncodingError 的流。"""
    body = response.content if response._content is not False else b""
    wrapped = requests.Response()
    wrapped.status_code = response.status_code
    wrapped.headers = response.headers.copy()
    wrapped._content = False  # 保持未消费状态，读取 body 时才触发失败
    wrapped.raw = _BrokenBodyStream(body)
    wrapped.request = request
    wrapped.url = request.url or ""
    return wrapped


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
            response = self._scenario.guard().call(
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

        # 流式 body 丢失：副作用已提交，响应头正常，body 读取时失败
        record = _new_record(self._scenario, records_before)
        if record is not None and record.fault is FaultKind.STREAM_BODY_LOSS:
            return _wrap_stream_body_loss(response, request)
        return response

    def close(self) -> None:
        self._base.close()
