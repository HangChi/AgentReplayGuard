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

**决策**：并行分支在 LangGraph 1.2.20 下是「superstep 内确定性顺序调度」，而非真线程并发。

**依据（实测）**：对 `a → (b, c) → END` 图（b 有 `time.sleep(0.05)` 制造时序差），同步
`invoke` 与异步 `ainvoke` 各连跑 5 次，`log` channel（`Annotated[list, operator.add]`）结果
**全部稳定**为 `['a', 'b', 'c']`——顺序由节点/边注册序决定，不因 sleep 抖动而变。

**关键推论**：
1. 同步 fan-out 下，effect 的 `sequence` / `attempt` / `_call_index` / `LogicalClock` 递增
   顺序**本就是确定的**（按 b→c 顺序）。因此「允许 fan-out 运行」后，同步路径的确定性
   无需新机制即可保持。
2. 不确定性只出现在**真正的并发交错**：异步节点在 await 点交错、或用户用
   `asyncio.gather` / 多线程手动并发调用 guard。这类交错会让全局计数器递增顺序依赖调度。
3. 并行分支写同一**无 reducer** 的 channel 会抛 `InvalidUpdateError`（`Annotated` + reducer
   才合法）——这是 LangGraph 层面的状态冲突，不是 side-effect 层问题，本特性不介入。

**被否决的方案**：为「真并发」引入全局锁或分布式时钟。理由：宪法第 II 条明确「任何
引入不确定性的设计 MUST 提供可关闭的确定性路径」，而真线程/真多进程并发本身不确定，
应通过「并发上下文归属 + 确定性排序」而非「锁」来保证可复现。真多线程并发列为 Out of
Scope（见 spec）。

---

## R-04 「线性一致性」的范围取舍

**决策**：以「并行分支重复副作用检测」为核心可判定目标，不追求完整的并发历史线性化
判定。

**依据**：严格意义的 linearizability 要求把每个并发操作映射到调用/响应区间内的一个点，
并证明存在合法串行序——这需要完整的并发历史（含未提交的读操作）。而本工具的 effect 只有
「提交」这一种可见操作，且 LangGraph fan-out 在当前版本是顺序调度，不存在真实的区间重叠
（见 R-03）。因此：

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

**决策**：引入「并发上下文」把 effect 归属到图节点/分支，扩展 `EffectRecord` 记录该归属。

**依据**：要让「并行重复」可解释（宪法第 VIII 条要求报告能定位），报告必须能回答「这次
重复是哪个分支造成的」。effect 是在用户节点函数内部通过 `guard.call` 记录的，`EffectGuard`
本身不知道调用发生在哪个节点。方案：LangGraph 1.2 提供 `langgraph.config.get_config()` 读取
运行时上下文，但更稳妥的是**线程/协程局部上下文**——在 `_find_fanout` 识别出分支后，为
每个分支建立确定性 branch_id，通过 contextvar 在分支执行期间注入，`EffectGuard._begin_attempt`
读取并写入 `EffectRecord`。

**被否决的方案**：
1. 通过 `langgraph.config` 运行时读取 node id——依赖 LangGraph 内部实现细节，易随版本漂移，
   且并发分支的 node id 与 effect 归属并非一一对应（一个 node 可多次调用 guard）。
2. 不记录分支归属，只复用 `NoDuplicateEffects`——丢失「并行 vs 串行重复」的区分能力，
   报告无法定位，违反宪法第 VIII 条。

---

## R-06 确定性策略：并发下的可复现

**决策**：并发上下文按**确定性顺序**分配 branch_id，effect 记录追加顺序保持「图结构序」，
不依赖真实完成时间排序。

**依据**：R-03 实测证明 LangGraph fan-out 同步/异步均为确定性顺序调度，故「允许运行」后
同步路径天然确定。异步真并发交错（await 点）场景列为 P3，通过 `started_tick` 区间重叠判定，
而非对记录重排序——避免引入非确定性的排序逻辑。

**被否决的方案**：按 `ended_tick` 对记录排序保证确定。理由：`ended_tick` 在并发下本身依赖
调度顺序，用它排序会放大不确定性；应保留「追加即顺序」的简单语义，把并发冲突的判定交给
区间重叠分析（区间由 `started_tick`/`ended_tick` 表达，两者在并发下仍是单调的）。

---

## Sources

- [LangGraph 持久化执行（durable execution）](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [LangGraph INVALID_CONCURRENT_GRAPH_UPDATE](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE)
- [Replaysafe](https://github.com/bittide/replaysafe)（幂等重试，AGPL）
- [agent-fault-harness](https://github.com/kish7/agent-fault-harness)（跨框架故障注入，MIT）
- [durabilitycurve agent-graph](https://durabilitycurve.com/tools/agent-graph)（state channel 审计）
- [Eval Mock](https://github.com/qianmoai/eval-mock)（确定性世界重放）
