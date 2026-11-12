# Data Model: 异步副作用安全测试

**Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

本特性不新增持久化实体，异步路径复用既有 `EffectRecord`、`RunSegment`、`ScenarioReport`。
以下记录的是异步语义下这些实体的字段约束与状态规则，确保与同步路径同构。

## 复用实体

### EffectRecord（异步语义）

| 字段 | 异步路径规则 |
|------|--------------|
| `effect_id` / `sequence` | 由场景内共享计数器生成；同步与异步混用时顺序仍单调递增 |
| `effect_type` | 来自 `effect` 声明，异步不改变命名规则 |
| `business_key` | 与同步相同的解析规则：参数名或 callable |
| `params_hash` | 与同步相同的规范化 JSON + SHA-256；排除业务键与幂等键参数 |
| `idempotency_key_hash` | 与同步相同；未提供时为 `None` |
| `attempt` | 按 `(effect_type, business_key)` 累计；同步与异步共用同一计数器 |
| `status` | `COMMITTED` / `NOT_COMMITTED` / `UNKNOWN`；异步不新增状态值 |
| `fault` | 与同步相同的五类故障枚举 |
| `error_type` / `error_message` | 异步异常记录真实类型；取消记录 `CancelledError` |
| `run_id` / `thread_id` / `checkpoint_id` | 由当前 run 上下文提供，异步入口必须建立同样的上下文 |
| `started_tick` / `ended_tick` | 逻辑时钟递增，不使用 wall clock |

> `ATTEMPTED` 状态保持现状（预留给未来流式/长任务），本特性不产生该状态。

### RunSegment（异步语义）

| 字段 | 异步路径规则 |
|------|--------------|
| `run_id` | 由 `Scenario._begin_run` 生成，与输入种类无关 |
| `input_kind` | 复用 `START` / `RESUME` / `INTERRUPT_RESUME` |
| `checkpoint_before` / `checkpoint_after` | 与同步入口相同的读取方式 |
| `interrupted` | 异步入口同样从输出中提取 `__interrupt__` |
| `error_type` / `error_message` | 异步图异常同样被捕获、记录并重新抛出 |

### ScenarioReport

不新增字段。异步失败报告复用 `format()` 与不变量结果，字段来源不变。

## 状态转换规则（异步）

```text
未开始 ──acall/acall_effect──▶ 尝试中（不落 ATTEMPTED 记录）
尝试中 ──正常返回──────────▶ COMMITTED
尝试中 ──函数抛 Exception───▶ NOT_COMMITTED（原样传播异常）
尝试中 ──提交前故障────────▶ NOT_COMMITTED（抛故障异常）
尝试中 ──提交后故障────────▶ COMMITTED（抛故障异常）
尝试中 ──CancelledError────▶ UNKNOWN（原样传播取消）
同步入口 ──收到 async 函数──▶ 抛 ScenarioConfigError（不写任何记录）
```

## 校验规则

- 业务键必须是非空字符串；异步路径与同步路径使用同一校验。
- 参数必须可 JSON 序列化；异步路径不改变错误类型。
- 幂等键必须为字符串或 `None`；异步路径不改变错误类型。
- 异步入口执行同步函数时，按同步函数正常执行，结果与 `call` 一致。
- 同步入口执行异步函数时，必须在参数解析与账本写入之前失败。
- 场景 `FINISHED` 后调用异步入口，与同步入口一致抛 `ScenarioStateError`。

## 关系

```text
Scenario 1 ── * EffectRecord
Scenario 1 ── * RunSegment
RunSegment 1 ── * EffectRecord（通过 run_id 关联，宽松归属）
```

异步不新增关系类型；`run_id` 的归属规则与 001 规格一致。
