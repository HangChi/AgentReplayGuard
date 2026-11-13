# Research: 并发与并行图的副作用竞态与线性一致性检测

**Feature**: 004-concurrent-parallel-graph
**Status**: Draft

本文件记录本特性的技术调研结论，每条决策附实测依据与被否决的方案。

---

## R-01 现状：fan-out 在入口即被拒绝

**决策**：`LangGraphAdapter._find_fanout()` 目前通过遍历 `graph.get_graph().edges` 里
非 conditional 边，统计 source 出现次数，发现任一 source 有 >1 条无条件出边即判定为
fan-out，`strict_graph=True`（默认）下直接抛 `UnsupportedGraphError`。

**依据（实测）**：对一个 `a → (b, c) → END` 的 fan-out 图，`get_graph().edges` 返回
`Edge(source='a', target='b', conditional=False)` 与 `Edge(source='a', target='c',
conditional=False)`，`_find_fanout()` 正确返回 `['a']`，入口抛
`UnsupportedGraphError: node 'a' has multiple unconditional outgoing edges; parallel
fan-out is not supported`。

**结论**：这是本特性的核心阻塞——用户一旦在图中使用并行分支，工具直接拒绝运行，连
检测机会都没有。001/002/003 三个 spec 均把「并行扇出」列为 Out of Scope，但并未论证
「检测并行重复副作用」本身无价值，而是当时的范围克制（宪法第 VII 条）。本特性把
「拒绝」改为「识别 + 支持 + 检测」。

---

## R-02 竞品调研：并行 side-effect 检测是真实空白

**决策**：本特性是真实能力缺口，非重复造轮子。

**调研对象与结论**（2026-11-13 检索）：

| 工具 | 类型 | 是否覆盖「并行 fan-out 副作用竞态检测」 |
|---|---|---|
| **Replaysafe**（npm/AGPL） | 幂等去重库（预防） | 否。做 `hash(type+target+input)` 去重，JS 生态，非测试定位 |
| **agent-fault-harness**（MIT） | 跨框架故障注入 harness（研究） | 部分。度量 duplicate side effect，但聚焦单工具调用 × 故障矩阵，不做并行图竞态 |
| **durabilitycurve / agent-graph** | LangGraph state 审计 | 部分。只审计 state channel 的 reducer 碰撞（静默状态损坏），不触及 side-effect 层 |
| **Eval Mock** 等确定性重放框架 | agent 评测 | 部分。确定性世界/重放，但未把「并行 fan-out + side-effect 线性一致性 + 确定性故障注入」三者结合 |

**被否决的方案**：直接复用 Replaysafe 或 agent-fault-harness。理由：前者是预防型运行时
依赖（引入第三方 runtime 依赖，违反宪法依赖策略），后者是研究 harness 而非 pytest 测试
工具，且都不做并行图的 side-effect 竞态检测。本特性是 AgentReplayGuard 自身定位
（确定性 pytest 测试工具）下的增量。

---

## R-03 LangGraph fan-out 的真实执行语义

**决策**：并行分支在 LangGraph 1.2.20 下是**真并发**——同步 fan-out 是线程池真并发，异步
fan-out 是协程交错。channel 合并顺序稳定 ≠ 节点执行顺序稳定。

**依据（实测，实现阶段修正）**：
1. 同步 fan-out 节点打印 `threading.get_ident()`，b/c 落在**不同线程**，且执行顺序交错
   （`b enter → c enter → c exit → b exit`，b sleep 期间 c 已完成）。
2. 异步 fan-out 节点同线程，但 await 点交错（协程并发）。
3. **effect 的 `sequence` 顺序在真并发下抖动**：两个并行分支各自 `guard.call` 不同 key，
   连跑 10 次，`sequence` 顺序在 `[('c',1),('b',2)]` 与 `[('b',1),('c',2)]` 之间交替。
4. 但 channel reducer 合并顺序（`['b','c']`）**稳定**——这正是最初「顺序调度」误判的来源：
   `log` 顺序稳定是 reducer 合并的确定性，掩盖了节点真并发执行的事实。

**关键推论（修正）**：
1. 同步 fan-out 下 effect 的 `sequence`/`attempt`/`_call_index`/`LogicalClock` 递增顺序
   **依赖调度、不可复现**。但**检测结论不依赖记录顺序**：`NoDuplicateEffects` 用
   `sorted(effect_ids)` 聚合，`committed_count` 用集合去重，均与追加顺序无关。
2. 因此「支持 fan-out」后的确定性承诺**收缩**为：
   - **确定**：branch 归属（来自 `get_config()['metadata']['langgraph_node']`，见 R-05）；
     检测结论（重复/并发/参数不一致，均排序后判定）；报告输出的违规列表（排序）。
   - **不确定（须文档标注）**：effect 记录的 `sequence`/`started_tick`/`ended_tick` 追加顺序。
     这正是宪法第 II 条「并发调度 MUST 标注」的情形。
3. 并行分支写同一**无 reducer** channel 抛 `InvalidUpdateError`，本特性不介入（原样传播）。

**被否决的方案**：为真并发引入全局锁 / 对记录强制排序。理由：锁改变用户图语义；对记录
排序放大不确定性且无必要（检测结论本就不依赖顺序）。采纳宪法第 II 条「标注 + 可关闭
确定性路径」：branch 归属确定、检测结论确定，仅追加顺序不确定并标注。

---

## R-04 「线性一致性」的范围取舍

**决策**：以「并行分支重复副作用检测」为核心可判定目标，不追求完整的并发历史线性化
判定。

**依据**：严格意义的 linearizability 要求把每个并发操作映射到调用/响应区间内的一个点，
并证明存在合法串行序——这需要完整的并发历史（含未提交的读操作）。而本工具的 effect 只有
「提交」这一种可见操作，且 LangGraph fan-out 在 1.2.20 是**真并发**（见 R-03），确实存在
真实的区间重叠。因此：

- **核心可判定目标**（本特性）：识别图结构 fan-out，允许其运行，记录 effect 的**分支归属**，
  新增不变量检测「多个并行分支提交了同一业务键」——这是「并行维度」下的重复副作用，是
  串行图里 retry/checkpoint 重复之外的**新来源**。
- **进阶**（P3，可判定但范围窄）：异步 await 交错 / 手动并发调用下的「同 key 并发提交」
  检测，基于 effect 的 `started_tick`/`ended_tick` 区间重叠判定。
- **不做**：跨 run 的完整并发历史线性化（需读操作语义，超出工具定位）。

**被否决的方案**：把「线性一致性」定义成通用线性化算法（如 Wing & Gong 的 WG 算法）。
理由：无读操作时算法退化为「同 key 是否并发提交」，复杂度不匹配价值，违反宪法第 VII 条。

---

## R-05 effect 分支归属的实现方案

**决策**：`EffectGuard` 通过 `langgraph.config.get_config()['metadata']['langgraph_node']`
读取当前图节点名作为 `branch_id`，扩展 `EffectRecord` 记录该归属。

**依据（实测，实现阶段修正）**：effect 是在用户节点函数内部通过 `guard.call` 记录的，
`EffectGuard` 本身不知道调用发生在哪个节点。实测发现：
1. `langgraph.config.get_config()` 返回的 `metadata['langgraph_node']` 在**真并发节点内正确
   隔离**——两个并行节点 b/c 各自 `get_config()['metadata']['langgraph_node']` 分别读到 `'b'`/`'c'`，
   互不串扰（连跑 3 次均正确）。这比 contextvar 更可靠：contextvar 会被线程池子线程继承
   父线程值，无法在真线程并发下区分分支。
2. `get_config()` 是 LangGraph 公开 API（`langgraph.config` 模块），稳定性有保证。

**被否决的方案**：
1. contextvar 注入——实测父线程 `set` 的值会被线程池子线程继承，真并发下无法区分分支；
   且适配器无 hook 在「节点执行期间」为每个分支分别 set（同步真线程并发下 set 时机不可控）。
2. 不记录分支归属，只复用 `NoDuplicateEffects`——丢失「并行 vs 串行重复」的区分能力，
   报告无法定位，违反宪法第 VIII 条。

**注意**：`get_config()` 只应在 `EffectGuard` 内部调用，且必须**降级**——当不在 LangGraph
运行上下文时（如 HTTP transport 适配器、独立调用 guard），`get_config()` 可能抛异常或返回
空，`branch_id` 回退为 `None`。核心模块 import `langgraph.config` 会破坏框架隔离（宪法第 V
条），故通过「可注入的 branch resolver」把框架依赖隔离在适配器层（见 plan）。

---

## R-06 确定性策略：并发下的可复现

**决策**：确定性承诺收缩为「branch 归属确定 + 检测结论确定」，effect 记录追加顺序不保证
确定（文档标注）。

**依据（实测，实现阶段修正）**：真并发下 effect 的 `sequence` 追加顺序抖动（R-03 实测
`[c,b]`/`[b,c]` 交替）。但：
- branch 归属来自 `get_config()['metadata']['langgraph_node']`，与调度无关，确定。
- `NoDuplicateEffects` 的 `commit_identity` 集合、`sorted(effect_ids)`、`committed_count`
  集合均与追加顺序无关，检测结论确定。
- `ConcurrentCommitDetected` 的区间重叠判定只依赖 `started_tick`/`ended_tick` 的相对关系，
  重叠判定结果不依赖记录先后。

**被否决的方案**：按 `ended_tick` 对记录排序保证确定。理由：`ended_tick` 在并发下本身依赖
调度顺序，用它排序会放大不确定性；且检测结论本就不依赖顺序，排序纯属多余。保留「追加即
顺序」的简单语义，把并发冲突判定交给区间重叠分析。

---

## Sources

- [LangGraph 持久化执行（durable execution）](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [LangGraph INVALID_CONCURRENT_GRAPH_UPDATE](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE)
- [Replaysafe](https://github.com/bittide/replaysafe)（幂等重试，AGPL）
- [agent-fault-harness](https://github.com/kish7/agent-fault-harness)（跨框架故障注入，MIT）
- [durabilitycurve agent-graph](https://durabilitycurve.com/tools/agent-graph)（state channel 审计）
- [Eval Mock](https://github.com/qianmoai/eval-mock)（确定性世界重放）
