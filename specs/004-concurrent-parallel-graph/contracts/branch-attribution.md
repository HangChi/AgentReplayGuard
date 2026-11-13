# Contract: 分支归属与并发判定

**Feature**: 004-concurrent-parallel-graph

本契约定义 fan-out 分支归属、`branch_id` 字段语义，以及并发提交判定的**判定顺序**与必须
满足的行为用例。

## 判定顺序（judgment order）

在 `Scenario.finish()` 生成报告前，effect 账本已按「追加顺序」完整记录。判定的顺序本身
就是契约：

1. **分支归属**（记录时）：`EffectGuard._begin_attempt` 在写 `EffectRecord` 时调用可注入的
   `branch_resolver` 获取当前分支，与 effect 的 attempt 一并落账。归属是**记录时确定**，非
   事后推断。LangGraph 上下文中 resolver 读 `metadata['langgraph_node']`，否则返回 `None`。
2. **去重/重复**（finish 时）：`NoDuplicateEffects` 按既有 `commit_identity` 去重口径判定。
   `branch_id` 不参与去重口径，仅作为报告定位信息。
3. **并发**（finish 时）：`ConcurrentCommitDetected` 对 COMMITTED 记录做区间重叠判定。
4. **报告**：`ScenarioReport.format()` 按既有确定性顺序输出，effect 行追加 `branch_id`
   （`None` 显示为空或 `-`）。

## `branch_id` 字段契约

- 类型 `str | None`；`None` 表示非 LangGraph 上下文（独立调用 / HTTP 适配器）。
- LangGraph 上下文中等于当前节点名（`metadata['langgraph_node']`），同一图结构下确定（串行
  图同样记录节点名）。
- 不同节点在同一 superstep 内，`branch_id` 必须互不相同（节点名天然唯一）。
- `branch_id` 不改变 `commit_identity`（不参与去重），仅用于报告定位。

## 行为用例表（must-have）

| # | 场景 | 期望 |
|---|------|------|
| BC-01 | 非 LangGraph 上下文（独立 guard 调用） | `branch_id is None` |
| BC-01b | 串行图 guard 记录 effect | `branch_id` = 产生 effect 的节点名 |
| BC-02 | fan-out 图，分支 b/c 各记录一条不同 key 的 effect | 两条记录 `branch_id` 分别为 b、c（节点名），且确定 |
| BC-03 | fan-out 图，两分支记录同一 key（无幂等键） | `NoDuplicateEffects` 报 `duplicate_effects`，`actual=2`，违规 effect_ids 两条，branch_id 不同 |
| BC-04 | 两分支记录同一 key + 相同幂等键 | `committed_count=1`，`ok=True` |
| BC-05 | 两分支记录同一 key + 相同幂等键 + 不同参数 | 报 `parameter_mismatch` |
| BC-06 | `asyncio.gather` 并发两个 `acall` 同一 key（无幂等键） | `ConcurrentCommitDetected` 报违规（区间重叠） |
| BC-07 | 两个 `acall` 顺序执行同一 key | 不报「并发」违规；`NoDuplicateEffects` 报重复 |
| BC-08 | 两 `acall` 并发但不同 key | 无违规 |
| BC-09 | 并行分支写同一无 reducer channel | LangGraph `InvalidUpdateError` 原样传播，工具不吞 |
| BC-10 | 同图结构连跑 20 次 fan-out | **检测结论与 branch_id 归属** 20/20 一致（追加 sequence 顺序可抖动，不断言） |
| BC-11 | 同步 `invoke` vs 异步 `ainvoke` 同 fan-out 图 | 检测结论、状态序列、attempt 归属、branch_id 一致 |

## 公开 API 变更面

- **新增**：`ConcurrentCommitDetected`（不变量类，对齐既有 `NoDuplicateEffects` 风格）。
- **扩展**：`EffectRecord` 增加 `branch_id: str | None` 字段（非破坏性——dataclass 追加字段，
  位置参数用户不应依赖；契约上属 minor）。
- **不变**：`Scenario`/`EffectGuard`/`LangGraphAdapter` 公开方法签名不变；`strict_graph`
  语义调整（见 spec FR-008），属行为变更而非签名变更。
