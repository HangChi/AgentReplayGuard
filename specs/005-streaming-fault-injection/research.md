# Research: 流式接口的副作用归属与故障注入

**Feature**: 005-streaming-fault-injection
**Status**: Draft

本文件记录流式接口（`astream` / `astream_events`）支持的技术调研结论，每条决策附实测依据
与被否决的方案。

---

## R-01 现状：适配器缺少流式入口

**决策**：`LangGraphAdapter` 目前只有 `invoke`/`ainvoke`/`resume`/`aresume`/
`resume_interrupt`/`aresume_interrupt` 六个入口，没有 `astream` / `astream_events`。

**依据（实测）**：`hasattr(adapter, 'astream')` 返回 `False`；适配器公开方法仅上述六个
（外加 `state`）。002 的 spec 里「异步执行」只覆盖了 `ainvoke`/`aresume`/`aresume_interrupt`，
`astream`/`astream_events` 明确列为 Out of Scope（002 spec「流式执行接口的故障注入与断言」）。

---

## R-02 绕过适配器直接 astream：effect 无归属

**决策**：这是本特性的核心动机——用户直接调 `graph.astream()`（绕过适配器）时，effect 能
记账但**丢失 run 归属与 branch 归属**。

**依据（实测）**：构造一个 `a → b` 串行图，两个节点各自 `guard.call` 记录 effect，直接
`graph.astream()` 执行：
```
chunk: {'a': {'log': ['a']}}
chunk: {'b': {'log': ['b']}}
effect 记录数: 2
  op key=K-A run=None branch=None
  op key=K-B run=None branch=None
```
两条 effect 都记录了，但 `run_id=None`、`branch_id=None`。原因：`_begin_run`（分配 run_id、
设置 thread/checkpoint、注入 branch resolver）只在适配器的 `_run`/`_arun` 里调用，直接调图
的流式方法不会触发。这导致：effect 成了「无主记录」，`NoDuplicateEffects` 仍能检测重复
（去重只看 effect_type+business_key），但报告无法回答「哪一次 run、哪个分支」。

---

## R-03 流式下的记账、故障注入、重试均正常

**决策**：无需为流式重做记账/故障注入/重试逻辑——它们复用 `guard.call` 在节点内正常工作，
流式只是执行入口不同。

**依据（实测）**：流式 + lost-ack 故障注入 + retry：
```
=== 流式 + lost-ack + retry ===
chunk: {'refund': {'log': ['refund']}}
effect 记录:
  attempt=1 status=committed fault=TIMEOUT_AFTER_COMMIT
  attempt=2 status=committed fault=None
committed_count: 2
ok: False
```
`NoDuplicateEffects` 正确检测到 2 条 committed。说明**故障注入与重试在 astream 下与 ainvoke
完全等价**，唯一缺的是归属层（R-02）。

---

## R-04 流式接口签名

**决策**：`astream` 与 `astream_events` 都是异步生成器，需在适配器中用 `async for` 驱动。

**依据（实测）**：
- `Pregel.astream` 参数：`input, config, context, stream_mode, print_mode, output_keys,
  interrupt_before, interrupt_after, durability, control, subgraphs, debug, version`。
- `Pregel.astream_events` 参数：`input, config, version, transformers`。
- `astream` 默认 `stream_mode='updates'`，每个 chunk 是 `{node_name: state_update}`。
- `astream_events` 事件类型：`on_chain_start` / `on_chain_stream` / `on_chain_end`（实测统计，
  无 `on_tool_start` 等，因为示例节点非工具调用）。
- 两者都是 `async_generator`，`astream_events` 需 `async for`（直接 `for` 会
  `TypeError: 'async_generator' object is not iterable`）。

---

## R-05 流式入口的归属策略

**决策**：`astream`/`astream_events` 包装成「异步上下文管理器」或「返回可迭代对象」，
在进入时 `_begin_run`（分配 run_id + 注入 branch resolver），在遍历完成后 `_finish_run`
（记录 RunSegment）。checkpoint 归属与 `ainvoke` 一致。

**依据**：`ainvoke` 的归属在 `_arun` 里完成：`checkpoint_before` → `_begin_run` →
`graph.ainvoke` → `_extract_interrupts` → `_finish_run`。流式需要同样的归属，但输出是
逐 chunk 产出的生成器，无法一次性 `finish_run`。方案：适配器提供 `astream()` 返回一个
包装后的异步生成器，`_begin_run` 在生成器首次迭代前执行，`_finish_run` 在生成器耗尽
（正常或异常）时执行。

**被否决的方案**：
1. 要求用户先调 `invoke` 再手动 `graph.astream()`——割裂，且 run_id 不连续，违背
   「用户接入零改动」的既有体验（003 传输层、004 分支都是透明接入）。
2. 只在 `astream` 结束时统一补记归属——流式是长生命周期，中途 effect 已经带着 `None`
   run_id 落账，事后补记需回写，破坏「只追加」的 EffectStore 语义。

---

## R-06 竞品调研：流式副作用检测是空白

**决策**：本特性是真实能力缺口，非重复造轮子。

**调研对象与结论**（2026-11-13 检索）：

| 工具 | 类型 | 是否覆盖「流式副作用归属 + 故障注入 + 重复检测」 |
|---|---|---|
| **ProofLayer**（prooflayer-rules） | 安全运行时中间件 | 部分。包装 invoke/stream/ainvoke/astream/stream_events/astream_events，但做的是**安全校验**（prompt injection、tool abuse、exfil、scope drift），非副作用重复检测 |
| **agent-fault-harness**（MIT） | 跨框架故障注入 harness | 部分。度量 duplicate side effects，但经代理层注入，不针对流式 effect 归属 |
| **LangSmith** | 官方 tracing/evals | 否。可观察性/评测，非确定性故障注入 + 副作用断言 |
| **Eval Mock / Replaysafe** | 评测/幂等预防 | 否（详见 004 research） |

**被否决的方案**：复用 ProofLayer 的包装器思路做副作用检测。理由：ProofLayer 是安全校验
中间件（拦截/替换/告警），本工具是确定性 pytest 测试工具，定位不同；且其引入运行时
中间件依赖，违反宪法依赖策略。本特性只在既有 `LangGraphAdapter` 上新增流式入口，复用
既有 EffectGuard/EffectStore/不变量，零新增依赖。

---

## Sources

- [LangGraph streaming 文档](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph astream_events API](https://docs.langchain.com/oss/python/langgraph/streaming-events)
- [ProofLayer LangGraph 集成](https://gunbark.dev/content/a16d3dd0-848c-4582-b2e5-f2601a24b189)
- [agent-fault-harness](https://github.com/kish7/agent-fault-harness)
