# Data Model: 流式接口的副作用归属与故障注入

**Feature**: 005-streaming-fault-injection

本特性**不新增、不修改任何数据结构**。`EffectRecord`、`RunSegment`、`ScenarioReport`、
`EffectStore`、`EffectStatus`、`FaultKind` 等全部复用 001–004 已定义的模型。

## 明确不做变更

- **不新增字段**：effect 的 `run_id`/`thread_id`/`checkpoint_id`/`branch_id` 已存在，本特性
  只是让它们在流式执行路径下也被正确填充（修复 research R-02 的 `None`）。
- **不新增实体**：无「流式 chunk 记录」「事件记录」等新结构；chunk/事件仅透传，不落账。
- **不新增存储**：复用进程内 Effect Store，无持久化。
- **不改枚举**：`RunInputKind` 复用既有 `START`（流式一次入口相当于一次 start run），
  不新增「STREAM」等值。

## 归属语义（流式与 ainvoke 一致）

| 字段 | ainvoke | astream / astream_events |
|------|---------|--------------------------|
| `run_id` | `_begin_run` 分配 `run-0001` | 相同 |
| `thread_id` | adapter 的 `thread_id` | 相同 |
| `checkpoint_id` | `_checkpoint_id()` 读 checkpointer | 相同（生成器开始前读一次） |
| `branch_id` | 经 resolver 读节点名 | 相同（resolver 在流式节点内仍生效） |

唯一差异：`RunSegment.output` 在流式下为 `None`（无单一最终返回值），`interrupts` 从 chunk
流中捕获。
