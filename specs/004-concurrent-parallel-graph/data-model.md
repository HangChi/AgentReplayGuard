# Data Model: 并发与并行图的分支归属与并发判定

**Feature**: 004-concurrent-parallel-graph

本文件只描述本特性**新增或写入**的数据结构，并明确声明不做哪些变更。

## 新增/扩展

### 1. `EffectRecord.branch_id`（扩展字段）

在现有 `EffectRecord` 上新增一个字段：

```
branch_id: str | None
```

- 语义：该 effect 由哪个并行分支提交；`None` 表示串行上下文（无 fan-out）或非图执行的
  独立 guarded 调用。
- 取值规则（确定性）：
  - 串行图 / 非 fan-out 区间：`None`
  - fan-out 区间内：`"b"`、`"c"` 这类分支短标识（见 BranchContext）
  - 嵌套 fan-out：层级表达（如 `"b.1"`），保证叶子分支唯一
- 约束：同一图结构 + 同 seed 下，`branch_id` 的赋值完全一致（FR-003 / SC-001）。

### 2. `BranchContext`（新增，`src/agentreplayguard/context.py`）

一个 contextvar 包装器，用于在分支执行期间注入 `branch_id`：

```
branch_id: ContextVar[str | None] = ContextVar("branch_id", default=None)
```

- 由适配器在分支执行前 `set`，执行后 `reset`；`EffectGuard._begin_attempt` 读取当前值。
- 因 LangGraph fan-out 是顺序调度（无真并发），单 contextvar 即足够表达「当前分支」。
- 核心模块通过读 contextvar 而非 import 适配器，保持框架隔离（宪法第 V 条）。

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
