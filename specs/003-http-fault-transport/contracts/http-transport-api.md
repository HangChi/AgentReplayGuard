# Public API Contract: HTTP 故障注入传输层

**Date**: 2026-11-13 | **Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)

本契约只描述 003 新增的公开接口。001/002 的函数级 guard、异步路径与报告 API 保持不变。

## 导入路径与可选依赖

```python
from agentreplayguard.adapters.httpx import (
    AsyncFaultyTransport,
    FaultyTransport,
    HttpEffect,
)
```

- 该模块 MUST 在未安装 `httpx` 时抛出 `ImportError`，错误信息 MUST 包含
  `pip install agentreplayguard[httpx]` 的安装提示。
- `import agentreplayguard` MUST NOT 导入该模块，MUST NOT 因缺少 httpx 失败。
- 支持的 httpx 版本范围：`>=0.27,<1.0`。

## HttpEffect

```python
@dataclass(frozen=True)
class HttpEffect:
    effect_type: str
    business_key: str
    params: Mapping[str, Any]
    idempotency_key: str | None = None
```

| 校验 | 行为 |
|------|------|
| `effect_type` 为空或非字符串 | 构造时抛 `ScenarioConfigError` |
| `business_key` 为空或非字符串 | 构造时抛 `ScenarioConfigError` |
| `params` 不可序列化为规范 JSON | 进入 guard 时抛 `ScenarioConfigError`，底层 transport 不被调用 |

## FaultyTransport / AsyncFaultyTransport

```python
ClassifyRequest = Callable[[httpx.Request], HttpEffect | None]


class FaultyTransport(httpx.BaseTransport):
    def __init__(
        self,
        base: httpx.BaseTransport,
        scenario: Scenario,
        classify: ClassifyRequest,
    ) -> None: ...

    def handle_request(self, request: httpx.Request) -> httpx.Response: ...

    def close(self) -> None: ...


class AsyncFaultyTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        base: httpx.AsyncBaseTransport,
        scenario: Scenario,
        classify: ClassifyRequest,
    ) -> None: ...

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response: ...

    async def aclose(self) -> None: ...
```

### 行为表

| 条件 | 账本 | 底层 transport | 调用方结果 |
|------|------|----------------|------------|
| `classify` 返回 `None` | 无新增 | 被调用一次 | 正常响应 |
| `classify` 抛异常 | 无新增 | 不被调用 | `ScenarioConfigError`，`__cause__` 保留原异常 |
| `classify` 返回非 `HttpEffect` | 无新增 | 不被调用 | `ScenarioConfigError` |
| `HttpEffect` 字段非法 | 无新增 | 不被调用 | `ScenarioConfigError` |
| 正常请求 | 1 条 `committed` | 被调用一次 | 正常响应 |
| 提交前故障 | 1 条 `not_committed` | 不被调用 | 对应 httpx 连接类异常 |
| 提交后故障 | 1 条 `committed` | 被调用一次 | 对应 httpx 读取类异常 |
| 底层抛业务异常 | 1 条 `not_committed` | 被调用一次 | 原异常原样传播 |
| 异步调用被取消 | 1 条 `unknown` | 被调用（可能已进入） | `asyncio.CancelledError` 传播 |

### 故障异常映射

| FaultKind | 抛出异常 |
|-----------|----------|
| `timeout_before_commit` | `httpx.ConnectTimeout` |
| `timeout_after_commit` | `httpx.ReadTimeout` |
| `connection_reset` | `httpx.ConnectError` |
| `server_error` | `httpx.HTTPStatusError`（`response.status_code == 500`） |
| `partial_success` | `httpx.ReadError` |

所有映射异常 MUST 携带原始 `request`，MUST 通过 `raise ... from exc` 保留 guard 异常为
`__cause__`。

## 生命周期与归属

- 调用前必须处于 `CREATED` 或 `RUNNING` 场景；`FINISHED` 后使用抛 `ScenarioStateError`
  （由 guard 提供，适配器不额外包装）。
- effect 的 `run_id` / `thread_id` / `checkpoint_id` 与调用时的场景上下文一致。
- `close()` / `aclose()` MUST 只委托底层 transport，不影响场景生命周期。

## 向后兼容

- 新增 extra 与模块，不改动任何既有导出签名。
- 不安装 httpx 时，现有测试、示例与 `import agentreplayguard` 行为不变。
