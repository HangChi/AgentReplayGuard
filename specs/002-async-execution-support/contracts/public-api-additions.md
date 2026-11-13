# Public API Additions: 异步副作用安全测试

**Date**: 2026-11-13 | **Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md)

本契约只描述 002 新增的公开接口；001 的同步接口保持不变（见
[001 public-api.md](../../001-effect-safety-testing/contracts/public-api.md)）。

## EffectGuard

```python
class EffectGuard:
    def effect(
        self,
        effect_type: str,
        *,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
    ) -> Callable[[F], F]: ...

    async def acall(
        self,
        effect_type: str,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        key: str | Callable[[Mapping[str, Any]], str],
        params: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        idempotency_key: str | Callable[[Mapping[str, Any]], str | None] | None = None,
        **kwargs: Any,
    ) -> T: ...
```

### `effect` 行为

| 被装饰函数 | 返回的 wrapper | 语义 |
|------------|----------------|------|
| `def f(...)` | 同步 wrapper | 与 001 完全一致 |
| `async def f(...)` | 异步 wrapper（可 await） | 每次 await 触发一次记账与故障注入 |

- 业务键、参数哈希、幂等键哈希、attempt 的解析与校验与同步完全一致。
- 装饰器本身不执行函数，不产生记录。
- 异步 wrapper 在每次 await 时产生一条记录；等待期间的取消见下表。

### `acall` 行为

| 输入 | 结果 |
|------|------|
| 同步函数正常返回 | 返回真实结果，记录 `COMMITTED` |
| 异步函数正常返回 | await 后返回真实结果，记录 `COMMITTED` |
| 函数抛 `Exception` | 记录 `NOT_COMMITTED`，原样传播 |
| 提交前故障 | 不执行函数，记录 `NOT_COMMITTED`，抛故障异常 |
| 提交后故障 | 执行函数，记录 `COMMITTED`，抛故障异常 |
| 异步函数被取消 | 记录 `UNKNOWN`，传播 `asyncio.CancelledError` |

### `call` 对异步函数的拒绝

| 条件 | 行为 |
|------|------|
| `call(..., async_fn)` | 在参数绑定与账本写入之前抛 `ScenarioConfigError`，账本零新增 |
| 错误信息 | 必须包含「异步函数请使用 acall / await」的可操作提示 |

## LangGraphAdapter

```python
class LangGraphAdapter:
    async def ainvoke(self, input: Mapping[str, Any] | None = None) -> GraphRun: ...

    async def aresume(self, input: Mapping[str, Any] | None = None) -> GraphRun: ...

    async def aresume_interrupt(self, value: Any = None) -> GraphRun: ...
```

### 前置条件与错误

| 方法 | 前置条件 | 违反时 |
|------|----------|--------|
| `ainvoke` | 图具备 `ainvoke`（构造时已要求 `invoke`/`get_state`/`get_graph`） | `UnsupportedGraphError` |
| `aresume` | 已存在前次 run；图有 checkpointer | `ScenarioConfigError` / `UnsupportedGraphError` |
| `aresume_interrupt` | 前次 run 处于 interrupted；图有 checkpointer | `ScenarioConfigError` / `UnsupportedGraphError` |

- 异步入口与同步入口共享 run 片段结构、effect 归属与报告格式。
- 图异常被记录到 `RunSegment` 后原样传播，与同步入口一致。
- 异步入口不改变 `strict_graph` 的并行扇出检查。

## 兼容性承诺

- 001 的公开函数签名、返回类型与异常类型不变。
- 新增方法不改变同步路径行为；未安装 langgraph 时核心包仍可导入。
- 不新增运行时第三方依赖。
