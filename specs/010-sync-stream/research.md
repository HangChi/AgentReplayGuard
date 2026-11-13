# Research: 同步 stream 入口（LangGraphAdapter）

**Feature**: 010-sync-stream
**Status**: Draft

## R-01 现状：只有异步 astream/astream_events，无同步 stream

**决策**：005 只加了异步 `astream`/`astream_events`；同步 `stream`/`stream_events` 明确列为
Out of Scope（005 spec「同步 stream / stream_events 可后续按需补充」）。

## R-02 同步 stream 是干净稳定的真同步生成器

**决策**：`Pregel.stream` 返回 `Iterator[dict]`（真同步生成器，`isasyncgenfunction=False`），
与 `astream`（`AsyncIterator`）对称。

**依据（实测）**：`stream()` 返回同步迭代器，`for chunk in cg.stream(...)` 直接可用，chunk
形态与 `astream` 一致（`{'node': {...}}`）。

## R-03 同步 stream_events：v2 不支持、v3 实验性

**决策**：同步 `stream_events` 列为 Out of Scope。

**依据（实测）**：
- `stream_events(version='v2')` 抛 `NotImplementedError: stream_events(version='v2') is not
  supported. Use astream_events() for v1/v2, or stream_events(version='v3')...`。
- `stream_events(version='v3')` 返回 `GraphRunStream`，但触发 `LangChainBetaWarning: The v3
  streaming protocol on Pregel is experimental`——实验性 API，不稳定。
- 依赖实验性 API 违反宪法第 II 条（确定性）与第 VII 条（YAGNI）；事件流需求用 `astream_events`
  （005 已提供）即可满足。

## R-04 同步 stream 的归属机制：复用 finally 收尾

**决策**：同步 `stream()` 用同步生成器 + `finally` 收尾，与 005 的 `astream` 对称，但不要求
`ainvoke` 能力（`stream` 是同步入口，底层用 `invoke` 驱动）。

**依据**：`stream` 是同步生成器，`_begin_run` 在首次迭代前、`_finish_run` 在 `finally` 中
执行，保证正常耗尽 / 异常 / `break` 三条路径收尾（同 005 的设计）。
