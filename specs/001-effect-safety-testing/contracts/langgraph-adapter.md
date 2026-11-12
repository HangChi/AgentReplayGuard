# Contract: LangGraph Adapter

**Feature**: `001-effect-safety-testing`
**Date**: 2026-11-12
**Scope**: 仅覆盖 LangGraph 1.2.x 的同步、串行图；不使用私有 API。

## 支持的运行形态

| 能力 | 要求 | MVP |
|------|------|-----|
| 首次执行 | `graph.invoke(input, config)` | 支持 |
| 节点重试 | `add_node(..., retry_policy=RetryPolicy(...))` | 支持（需显式 retry_on） |
| Checkpoint 恢复 | `graph.invoke(None, config)` + checkpointer | 支持 |
| Interrupt 恢复 | `graph.invoke(Command(resume=...), config)` | 支持 |
| 并行分支 | 同一 superstep 多节点 | 不支持 |
| 异步节点 | `ainvoke` / async node | 不支持 |
| 流式事件 | `stream_events` / `stream` | 不支持 |
| 子图作为工具 | 嵌套图内部副作用 | 尽力支持，MVP 不承诺 |

## Graph 前置条件

- 必须是已编译的 graph 对象，具备 `invoke`、`get_state`、`get_graph`。
- 需要 resume / interrupt 时，编译必须带 checkpointer（推荐 `InMemorySaver`）：

```python
from langgraph.checkpoint.memory import InMemorySaver
graph = builder.compile(checkpointer=InMemorySaver())
```

- 节点中的副作用工具必须用 `scenario.guard()` 包装后使用；未包装的副作用不在检测范围内。
- `RetryPolicy` 必须显式配置 `retry_on`（见下节），否则默认策略不会重试超时/连接异常。

## 重试配置契约（关键）

LangGraph 默认 `retry_on=default_retry_on` **排除 `OSError`**，而 `TimeoutError` 与
`ConnectionError` 都是 `OSError` 子类。示例与文档必须使用：

```python
from langgraph.types import RetryPolicy

RetryPolicy(
    max_attempts=3,
    retry_on=(TimeoutError, ConnectionError, ServiceError),
    initial_interval=0,   # 避免真实等待，保证 <5s
    jitter=False,         # 避免时间抖动
)
```

注意：`ServiceError` 是本项目的模拟 5xx 异常；真实 SDK 的 5xx 异常需用户按同样方式加入
`retry_on`。

## 调用序列契约

### 1. 首次执行（含节点重试）

```text
adapter.invoke(input)
  ├─ checkpoint_before = get_state(config)?.checkpoint_id
  ├─ scenario 进入 RUNNING，创建 RunSegment(run-0001, START)
  ├─ graph.invoke(input, config)
  │    └─ node attempt 1 → guard.call → fault? → 记录 effect
  │    └─ node attempt 2（RetryPolicy 命中）→ guard.call → 记录 effect
  └─ checkpoint_after = get_state(config)?.checkpoint_id
       └─ RunSegment COMPLETED；返回 GraphRun
```

**契约**:
- 每次节点重试都会经过 guard，因此 attempt 逐次递增，effect 记录不会丢失。
- 若 `graph.invoke` 抛异常，RunSegment 标记 FAILED，异常原样抛出；场景仍可 `resume`。
- 返回的 `GraphRun.output` 为最后一次 invoke 的结果（通常为 dict）。

### 2. Checkpoint 恢复

```text
adapter.resume(input=None)
  ├─ 要求存在 prior run
  ├─ checkpoint_before = get_state(config)?.checkpoint_id
  ├─ 创建 RunSegment(run-0002, RESUME)
  ├─ graph.invoke(None, config)   # 从最新 checkpoint 继续
  └─ 返回 GraphRun；effect 记录归属 run-0002
```

**契约**:
- 没有 prior run 时调用 resume → `ScenarioConfigError`。
- 恢复后是否重复执行 effect 由 LangGraph 的 checkpoint 语义决定，适配器不做干预，只记录。
- 每次 resume 生成新的 run_id；effect 的 `attempt` 在场景内继续累计，不重置。

### 3. Interrupt 恢复

```text
adapter.invoke(input)
  └─ output["__interrupt__"] 存在 → RunSegment INTERRUPTED，GraphRun.interrupted=True

adapter.resume_interrupt(value)
  ├─ 要求上一次 RunSegment 为 INTERRUPTED
  ├─ 创建 RunSegment(run-0002, INTERRUPT_RESUME)
  ├─ graph.invoke(Command(resume=value), config)
  └─ 节点从头重跑 → guard 再次记录 effect（如果 effect 在 interrupt 之前）
```

**契约**:
- 上一次未中断时调用 `resume_interrupt` → `ScenarioConfigError`。
- `interrupts` 从 `output["__interrupt__"]` 提取为元组；没有则为空。
- 官方文档明确「恢复时节点从头执行」，因此 interrupt 前的副作用必须被本工具捕获并报告。

## 运行片段与 effect 归属

- `run_id` 由适配器生成（`run-0001` 起），只在本场景内唯一。
- `thread_id` 默认 `thread-0001`，可由构造函数覆盖；同一 adapter 的所有片段共享。
- `checkpoint_before` / `checkpoint_after` 是片段级归属，不是每个 effect 的精确 checkpoint；
  MVP 不解析节点内部 task 级 checkpoint。
- guard 从场景的当前运行上下文读取 `run_id/thread_id/checkpoint_id`；适配器在调用 graph 前
  设置上下文，调用结束后清理。

## 图形态检查

`strict_graph=True`（默认）时：

1. 缺少 `invoke` / `get_state` / `get_graph` → `UnsupportedGraphError`。
2. `resume` / `resume_interrupt` 但 graph 无 checkpointer → `UnsupportedGraphError`。
3. `get_graph()` 中同一节点存在多条无条件出边（静态 fan-out）→ `UnsupportedGraphError`。

`strict_graph=False` 时跳过第 3 项，并在报告中记录 warning。条件边可能造成静态 fan-out
误报；MVP 选择保守失败，避免给出不可信结论。

## 契约测试清单

集成测试必须覆盖：

1. 默认 `RetryPolicy` 不重试 `TimeoutError`（证明文档警告的必要性）。
2. 显式 `retry_on` 时重试发生，guard 记录 attempt 1/2，报告检测到重复。
3. 相同场景 + seed 连续 20 次，effect 计数与结论一致。
4. Checkpoint 位于 effect 之后，resume 不新增 committed effect。
5. Checkpoint 位于 effect 之前，resume 新增 effect 并被检测。
6. Interrupt 前有 effect：resume 后重复；Interrupt 后有 effect：resume 后不重复。
7. 未设置 checkpointer 时 resume → `UnsupportedGraphError`。
8. 并行 fan-out 图在 `strict_graph=True` 下 → `UnsupportedGraphError`。

## 已知限制

- 不检测节点内部 task 级 checkpoint；恢复粒度以 RunSegment 为准。
- 不保证子图内部未包装的副作用被记录。
- 不检测真正的并发竞态（MVP 仅串行图）。
- LangGraph 2.x 不在支持范围；升级需重新验证公共 API 与默认重试策略。
