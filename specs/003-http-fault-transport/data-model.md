# Data Model: HTTP 故障注入传输层

**Date**: 2026-11-13 | **Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## 实体 1：HttpEffect（新增，内存值对象）

分类函数从 `httpx.Request` 提取的副作用语义。不可变；不持久化原始请求体。

| 字段 | 类型 | 必填 | 校验规则 |
|------|------|------|----------|
| `effect_type` | `str` | 是 | 非空；与函数级 guard 的 effect 类型使用同一命名空间 |
| `business_key` | `str` | 是 | 非空字符串；由 guard 再次校验，空值快速失败 |
| `params` | `Mapping[str, Any]` | 是 | 必须可序列化为规范 JSON；不可序列化时快速失败 |
| `idempotency_key` | `str \| None` | 否 | 缺省为 `None`；非空时参与幂等键哈希 |

**来源**：用户提供的 `classify(request)` 返回值；返回 `None` 表示该请求不参与记账。

**关系**：一个 `HttpEffect` 对应一次 `EffectGuard.call/acall`，最终产生一条既有
`EffectRecord`（不新增记录字段）。

## 实体 2：Http Transport 适配器（新增，行为对象）

| 属性/方法 | 同步 `FaultyTransport` | 异步 `AsyncFaultyTransport` |
|-----------|------------------------|-----------------------------|
| 构造参数 | `base: httpx.BaseTransport`、`scenario: Scenario`、`classify` | `base: httpx.AsyncBaseTransport`、`scenario: Scenario`、`classify` |
| 请求入口 | `handle_request(request)` | `async handle_async_request(request)` |
| 关闭 | `close()` 委托 `base.close()` | `async aclose()` 委托 `base.aclose()` |
| 记账调用 | `scenario.guard().call(...)` | `scenario.guard().acall(...)` |
| 未匹配请求 | 直接调用 `base.handle_request` | 直接 `await base.handle_async_request` |

**状态**：无自身状态；所有状态（attempt、故障计划、记录）由 `Scenario` 持有。

## 实体 3：请求到 Effect 的映射规则

| 阶段 | 行为 |
|------|------|
| 分类 | `classify(request)`；抛异常或返回非 `HttpEffect` → `ScenarioConfigError` |
| 未匹配 | 返回 `None` → 透传，账本零新增，故障计划不消耗 |
| 参数绑定 | 以 `{"request": request}` 作为 guard 的参数映射；`params` / `idempotency_key` 由 `HttpEffect` 提供 |
| 记账 | guard 生成 attempt、参数哈希、幂等键哈希与 run/thread/checkpoint 归属 |
| 提交边界 | 底层 transport 返回响应（响应头到达）即视为已提交 |

## 故障到客户端异常的映射

| FaultKind | EffectStatus | 抛出异常 | 构造参数 |
|-----------|--------------|----------|----------|
| `timeout_before_commit` | `not_committed` | `httpx.ConnectTimeout` | `message`、`request=request` |
| `timeout_after_commit` | `committed` | `httpx.ReadTimeout` | `message`、`request=request` |
| `connection_reset` | `not_committed` | `httpx.ConnectError` | `message`、`request=request` |
| `server_error` | `not_committed` | `httpx.HTTPStatusError` | `message`、`request`、`response=httpx.Response(500, request=request)` |
| `partial_success` | `committed` | `httpx.ReadError` | `message`、`request=request` |

**判定依据**：捕获 guard 异常后，取本次调用新增的 `EffectRecord`；仅当
`record.fault is not None` 时执行映射。无新增记录或 `fault is None` 时原样传播异常。

## 复用实体

- **EffectRecord / EffectStore**：字段与语义完全不变；HTTP 尝试与函数级尝试共用账本。
- **FaultPlan / FaultRule**：按 effect_type、business_key、attempt、call_index 匹配；
  HTTP 请求同样消耗 `call_index`。
- **ScenarioReport / 不变量**：报告与重复检测不感知传输层，无需新字段。
