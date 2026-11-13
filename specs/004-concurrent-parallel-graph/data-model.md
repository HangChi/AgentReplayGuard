# Data Model: 并发与并行图的分支归属与并发判定

**Feature**: 004-concurrent-parallel-graph

本文件只描述本特性**新增或写入**的数据结构，并明确声明不做哪些变更。

## 新增/扩展

### 1. `EffectRecord.branch_id`（扩展字段）

在现有 `EffectRecord` 上新增一个字段：

```
branch_id: str | None
```

- 语义：该 effect 由哪个图节点（分支）提交；`None` 表示非 LangGraph 上下文（串行图外的
  独立 guarded 调用、HTTP 适配器等）。
- 取值规则（确定性）：
  - 串行图 / 非 LangGraph 上下文：`None`
  - LangGraph 上下文：当前节点名（`metadata['langgraph_node']`），如 `"notify"`、`"deduct"`
- 约束：同一图结构下，`branch_id` 的赋值完全一致（与调度无关，FR-003 / SC-001）。

### 2. `branch_resolver`（新增可注入回调）

一个可注入的 `Callable[[], str | None]`，用于在 effect 记录时获取当前分支归属：

```
EffectGuard._branch_resolver: Callable[[], str | None]
```

- 默认返回 `None`（串行/独立调用/HTTP 适配器）。
- `LangGraphAdapter` 构造时注入「读 `langgraph.config.get_config()['metadata']['langgraph_node']`」
  的 resolver，从而把框架依赖隔离在适配器层（核心模块不 import LangGraph，宪法第 V 条）。
- `EffectGuard._begin_attempt` 调用 resolver 写入 `EffectRecord.branch_id`。
- resolver 在真并发节点内正确隔离（`get_config` 按 task 上下文返回各自节点名，实测 R-05）。

### 3. `ConcurrentCommitDetected`（新增不变量，`src/agentreplayguard/invariants.py`）

检测「同一业务键被并发提交」：

- 判定：对同一 `(effect_type, business_key)` 的两条 COMMITTED 记录，若
  `a.started_tick < b.ended_tick and b.started_tick < a.ended_tick`（区间重叠），判定为并发。
- 注意：`started_tick`/`ended_tick` 是既有逻辑时钟字段，本特性直接复用，不新增时间字段。
- 与 `NoDuplicateEffects` 正交：前者判「并发」，后者判「重复」。并发重复场景两个都可能触发。

## 明确不做变更

- `EffectRecord` 的其余字段（effect_id/sequence/attempt/status/fault/run_id/...）语义不变。
- `EffectStatus`、`FaultKind` 枚举不新增值（并发不引入新状态）。
- `EffectStore` 的查询接口不变（`branch_id` 通过 `EffectRecord` 直接可见，不新增查询方法，
  除非 US2 报告需要按分支聚合——若需要，聚合逻辑放 report/invariants，不放 store）。
- 不新增持久化、不新增存储后端。
