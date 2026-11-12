"""EffectGuard：参数绑定、哈希、attempt 累计与故障接线。"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast

from .clock import LogicalClock
from .effects import EffectRecord, EffectStatus, EffectStore
from .errors import ScenarioConfigError
from .faults import FaultInjector, FaultKind, fault_exception, is_before_commit

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

_MAX_ERROR_MESSAGE = 500


def _canonical_json(obj: Any) -> str:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ScenarioConfigError(f"params are not JSON-serializable: {exc}") from exc


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_ERROR_MESSAGE else text[:_MAX_ERROR_MESSAGE]


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
        bound = inspect.signature(fn).bind(*args, **kwargs)
        arg_map: dict[str, Any] = dict(bound.arguments)

        business_key = self._resolve_key(key, arg_map)
        params_map = self._resolve_params(params, arg_map, key, idempotency_key)
        params_hash = _sha256(_canonical_json(params_map))
        idempotency_key_hash = self._resolve_idempotency_hash(idempotency_key, arg_map)

        attempt = self._store._next_attempt(effect_type, business_key)
        directive = self._injector.next_directive(effect_type, business_key, attempt)
        run_id, thread_id, checkpoint_id = self._run_context()

        started_tick = self._clock.tick()

        def record(
            status: EffectStatus,
            *,
            fault: FaultKind | None = None,
            error_type: str | None = None,
            error_message: str | None = None,
        ) -> None:
            self._record(
                effect_type=effect_type,
                business_key=business_key,
                params_hash=params_hash,
                idempotency_key_hash=idempotency_key_hash,
                attempt=attempt,
                status=status,
                fault=fault,
                error_type=error_type,
                error_message=error_message,
                run_id=run_id,
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                started_tick=started_tick,
            )

        if directive is not None and is_before_commit(directive.kind):
            exc = fault_exception(directive.kind)
            record(
                EffectStatus.NOT_COMMITTED,
                fault=directive.kind,
                error_type=type(exc).__name__,
                error_message=_truncate(str(exc)),
            )
            raise exc

        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            record(
                EffectStatus.NOT_COMMITTED,
                error_type=type(exc).__name__,
                error_message=_truncate(str(exc)),
            )
            raise

        if directive is not None and not is_before_commit(directive.kind):
            fault_exc = fault_exception(directive.kind)
            record(
                EffectStatus.COMMITTED,
                fault=directive.kind,
                error_type=type(fault_exc).__name__,
                error_message=_truncate(str(fault_exc)),
            )
            raise fault_exc

        record(EffectStatus.COMMITTED)
        return result

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

    def _record(
        self,
        *,
        effect_type: str,
        business_key: str,
        params_hash: str,
        idempotency_key_hash: str | None,
        attempt: int,
        status: EffectStatus,
        fault: FaultKind | None,
        error_type: str | None,
        error_message: str | None,
        run_id: str | None,
        thread_id: str | None,
        checkpoint_id: str | None,
        started_tick: int,
    ) -> None:
        record = EffectRecord(
            effect_id=self._store._next_effect_id(),
            sequence=self._store._next_sequence(),
            effect_type=effect_type,
            business_key=business_key,
            params_hash=params_hash,
            idempotency_key_hash=idempotency_key_hash,
            attempt=attempt,
            status=status,
            fault=fault,
            error_type=error_type,
            error_message=error_message,
            run_id=run_id,
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            started_tick=started_tick,
            ended_tick=self._clock.tick(),
        )
        self._store._append(record)
