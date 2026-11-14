"""HTTP 适配层共享结构：副作用语义描述与分类辅助。

仅依赖标准库，供 httpx 与 requests 适配器共用，避免任一可选依赖的导入耦合。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from ..errors import ScenarioConfigError

__all__ = ["HttpEffect"]

# 请求类型泛化：httpx.Request 与 requests.PreparedRequest 都有 method/url 属性
_Request = TypeVar("_Request")


@dataclass(frozen=True)
class HttpEffect:
    """分类函数从请求中提取的副作用语义。不持久化原始请求内容。"""

    effect_type: str
    business_key: str
    params: Mapping[str, Any]
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.effect_type, str) or not self.effect_type:
            raise ScenarioConfigError("HttpEffect.effect_type must be a non-empty str")
        if not isinstance(self.business_key, str) or not self.business_key:
            raise ScenarioConfigError("HttpEffect.business_key must be a non-empty str")
        if not isinstance(self.params, Mapping):
            raise ScenarioConfigError("HttpEffect.params must be a mapping")
        if self.idempotency_key is not None and not isinstance(self.idempotency_key, str):
            raise ScenarioConfigError("HttpEffect.idempotency_key must be a str or None")


def classify_or_raise(
    classify: Callable[[_Request], HttpEffect | None],
    request: _Request,
) -> HttpEffect | None:
    """执行分类回调；把非预期异常统一包装为配置错误。"""
    try:
        effect = classify(request)
    except ScenarioConfigError:
        raise
    except Exception as exc:
        method = getattr(request, "method", "?")
        url = getattr(request, "url", "?")
        raise ScenarioConfigError(f"classify failed for {method} {url}: {exc}") from exc
    if effect is None:
        return None
    if not isinstance(effect, HttpEffect):
        raise ScenarioConfigError(
            f"classify must return HttpEffect | None, got {type(effect).__name__}"
        )
    return effect
