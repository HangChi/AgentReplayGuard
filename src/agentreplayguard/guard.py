"""EffectGuard：参数绑定、哈希、attempt 累计与故障接线（同步 + 异步）。"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from .clock import LogicalClock
from .effects import EffectRecord, EffectStatus, EffectStore
from .errors import ScenarioConfigError
from .faults import (
    FaultDirective,
    FaultInjector,
    FaultKind,
    fault_exception,
    is_before_commit,
)

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

_MAX_ERROR_MESSAGE = 500

_ASYNC_MISUSE_MESSAGE = (
    "async effect functions must be awaited via the async path: "
    "use `await guard.acall(...)` or `await` the decorated async tool"
)


def _canonical_json(obj: Any) -> str:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ScenarioConfigError(f"params are not JSON-serializable: {exc}") from exc


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_ERROR_MESSAGE else text[:_MAX_ERROR_MESSAGE]


@dataclass(frozen=True)
class _Attempt:
    """一次已准备好的副作用尝试：解析结果、故障判定与归属信息。"""

    effect_type: str
    business_key: str
    params_hash: str
    idempotency_key_hash: str | None
    attempt: int
    directive: FaultDirective | None
    run_id: str | None
    thread_id: str | None
    checkpoint_id: str | None
    started_tick: int


class EffectGuard:
    """包裹有副作用的调用，记录每次尝试并注入确定性故障。"""

    def __init__(
        self,
        store: EffectStore,
        clock: LogicalClock,
        injector: FaultInjector,
        *,
        run_context: Callable[[], tuple[str | None, str | None, str | None]],
        check_state: Callable[[], None],
    ) -> None:
        self._store = store
        self._clock = clock
        self._injector = injector
        self._run_context = run_context
        self._check_state = check_state

    def effect(
        self,
        effect_type: str,
        *,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
    ) -> Callable[[F], F]:
        def decorator(fn: F) -> F:
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await self.acall(
                        effect_type,
                        fn,
                        *args,
                        key=key,
                        params=params,
                        idempotency_key=idempotency_key,
                        **kwargs,
                    )

                return cast(F, async_wrapper)

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return self.call(
                    effect_type,
                    fn,
                    *args,
                    key=key,
                    params=params,
                    idempotency_key=idempotency_key,
                    **kwargs,
                )

            return cast(F, wrapper)

        return decorator

    def call(
        self,
        effect_type: str,
        fn: Callable[..., T],
        *args: Any,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
        **kwargs: Any,
    ) -> T:
        self._check_state()
        if inspect.iscoroutinefunction(fn):
            raise ScenarioConfigError(_ASYNC_MISUSE_MESSAGE)
        attempt = self._begin_attempt(
            effect_type,
            fn,
            args,
            kwargs,
            key=key,
            params=params,
            idempotency_key=idempotency_key,
        )
        self._raise_if_before_commit(attempt)

        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            self._record_outcome(
                attempt,
                EffectStatus.NOT_COMMITTED,
                error_type=type(exc).__name__,
                error_message=_truncate(str(exc)),
            )
            raise

        self._raise_if_after_commit(attempt)
        self._record_outcome(attempt, EffectStatus.COMMITTED)
        return result

    async def acall(
        self,
        effect_type: str,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
        **kwargs: Any,
    ) -> T:
        self._check_state()
        attempt = self._begin_attempt(
            effect_type,
            fn,
            args,
            kwargs,
            key=key,
            params=params,
            idempotency_key=idempotency_key,
        )
        self._raise_if_before_commit(attempt)

        try:
            result = await self._invoke(fn, args, kwargs)
        except asyncio.CancelledError as exc:
            self._record_outcome(
                attempt,
                EffectStatus.UNKNOWN,
                error_type=type(exc).__name__,
                error_message=_truncate(str(exc)),
            )
            raise
        except Exception as exc:
            self._record_outcome(
                attempt,
                EffectStatus.NOT_COMMITTED,
                error_type=type(exc).__name__,
                error_message=_truncate(str(exc)),
            )
            raise

        self._raise_if_after_commit(attempt)
        self._record_outcome(attempt, EffectStatus.COMMITTED)
        return cast("T", result)

    # 内部实现

    @staticmethod
    async def _invoke(
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """同步函数直接执行；异步函数 await 后返回。"""
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return fn(*args, **kwargs)

    def _begin_attempt(
        self,
        effect_type: str,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None,
    ) -> _Attempt:
        bound = inspect.signature(fn).bind(*args, **kwargs)
        arg_map: dict[str, Any] = dict(bound.arguments)

        business_key = self._resolve_key(key, arg_map)
        params_map = self._resolve_params(params, arg_map, key, idempotency_key)
        params_hash = _sha256(_canonical_json(params_map))
        idempotency_key_hash = self._resolve_idempotency_hash(idempotency_key, arg_map)

        attempt = self._store._next_attempt(effect_type, business_key)
        directive = self._injector.next_directive(effect_type, business_key, attempt)
        run_id, thread_id, checkpoint_id = self._run_context()

        return _Attempt(
            effect_type=effect_type,
            business_key=business_key,
            params_hash=params_hash,
            idempotency_key_hash=idempotency_key_hash,
            attempt=attempt,
            directive=directive,
            run_id=run_id,
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            started_tick=self._clock.tick(),
        )

    def _raise_if_before_commit(self, attempt: _Attempt) -> None:
        directive = attempt.directive
        if directive is None or not is_before_commit(directive.kind):
            return
        exc = fault_exception(directive.kind)
        self._record_outcome(
            attempt,
            EffectStatus.NOT_COMMITTED,
            fault=directive.kind,
            error_type=type(exc).__name__,
            error_message=_truncate(str(exc)),
        )
        raise exc

    def _raise_if_after_commit(self, attempt: _Attempt) -> None:
        directive = attempt.directive
        if directive is None or is_before_commit(directive.kind):
            return
        exc = fault_exception(directive.kind)
        self._record_outcome(
            attempt,
            EffectStatus.COMMITTED,
            fault=directive.kind,
            error_type=type(exc).__name__,
            error_message=_truncate(str(exc)),
        )
        raise exc

    def _resolve_key(
        self,
        key: str | Callable[[Mapping[str, Any]], str],
        arg_map: Mapping[str, Any],
    ) -> str:
        if callable(key):
            value: Any = key(dict(arg_map))
        else:
            if key not in arg_map:
                raise ScenarioConfigError(f"key parameter {key!r} not found in arguments")
            value = arg_map[key]
        if not isinstance(value, str) or not value:
            raise ScenarioConfigError(f"business key must be a non-empty str, got {value!r}")
        return value

    def _resolve_params(
        self,
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
        arg_map: Mapping[str, Any],
        key: str | Callable[[Mapping[str, Any]], str],
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None,
    ) -> Mapping[str, Any]:
        if params is not None:
            result: Any = params(dict(arg_map))
        else:
            result = dict(arg_map)
            if isinstance(key, str):
                result.pop(key, None)
            if isinstance(idempotency_key, str):
                result.pop(idempotency_key, None)
        if not isinstance(result, Mapping):
            raise ScenarioConfigError("params must return a mapping")
        return result

    def _resolve_idempotency_hash(
        self,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None,
        arg_map: Mapping[str, Any],
    ) -> str | None:
        if idempotency_key is None:
            return None
        if callable(idempotency_key):
            value: Any = idempotency_key(dict(arg_map))
        else:
            value = arg_map.get(idempotency_key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ScenarioConfigError("idempotency_key must be a str or None")
        return _sha256(value)

    def _record_outcome(
        self,
        attempt: _Attempt,
        status: EffectStatus,
        *,
        fault: FaultKind | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        record = EffectRecord(
            effect_id=self._store._next_effect_id(),
            sequence=self._store._next_sequence(),
            effect_type=attempt.effect_type,
            business_key=attempt.business_key,
            params_hash=attempt.params_hash,
            idempotency_key_hash=attempt.idempotency_key_hash,
            attempt=attempt.attempt,
            status=status,
            fault=fault,
            error_type=error_type,
            error_message=error_message,
            run_id=attempt.run_id,
            thread_id=attempt.thread_id,
            checkpoint_id=attempt.checkpoint_id,
            started_tick=attempt.started_tick,
            ended_tick=self._clock.tick(),
        )
        self._store._append(record)
