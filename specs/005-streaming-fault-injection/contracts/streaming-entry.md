# Contract: 流式入口

**Feature**: 005-streaming-fault-injection

本契约定义 `LangGraphAdapter` 的 `astream` / `astream_events` 入口的判定顺序与必须满足的
行为用例。

## 判定顺序（judgment order）

流式执行的归属生命周期是契约核心：

1. **进入**：`astream`/`astream_events` 被调用时先 `_ensure_async_capable()`（校验
   `ainvoke` 能力，缺失抛 `UnsupportedGraphError`）。
2. **开始迭代**：生成器首次 `__anext__` 前，`checkpoint_before = _checkpoint_id()` →
   `run_id = _begin_run(...)` → `started_tick = _tick()`。
3. **产出**：逐 chunk/事件透传底层 `graph.astream`/`astream_events`；遍历时累积
   `interrupts`（含 `__interrupt__` 的 chunk）。
4. **收尾**：`finally` 中 `_finish_run(...)`（正常耗尽 / 异常 / GeneratorExit 均执行）。
5. **报告**：`finish()` 后 `RunSegment` 与 effect 归属可查询。

## 行为用例表（must-have）

| # | 场景 | 期望 |
|---|------|------|
| SE-01 | 串行图 `adapter.astream` 遍历 | chunk 原样产出；effect `run_id`/`branch_id` 正确 |
| SE-02 | 串行图 `adapter.astream` 后 `finish()` | RunSegment `input_kind=start`、`run_id=run-0001` |
| SE-03 | 同图 `ainvoke` vs `astream` | effect 记录数/状态/attempt/branch 一致 |
| SE-04 | lost-ack + retry 图 `astream` | `committed_count=2`、`ok=False` |
| SE-05 | 提交前故障图 `astream` | effect `not_committed`、异常在迭代中抛出 |
| SE-06 | `adapter.astream_events(version='v2')` 遍历 | 事件原样产出；effect 归属正确 |
| SE-07 | 节点抛异常 | `_finish_run` 记录 error_type；异常原样抛出；无脏 run |
| SE-08 | `break` 提前退出 `async for` | `_finish_run` 正常收尾（error_type=None） |
| SE-09 | 缺 `ainvoke` 的图调 `astream` | 抛 `UnsupportedGraphError` |
| SE-10 | `astream(stream_mode='values')` | 参数透传，归属与默认 mode 一致 |

## 公开 API 变更面

- **新增**：`LangGraphAdapter.astream(...)` → 异步生成器；`LangGraphAdapter.astream_events(...)`
  → 异步生成器。
- **不变**：既有六个方法的签名与行为；`EffectRecord`/`RunSegment`/`ScenarioReport` 结构不变。
- **版本**：minor bump 0.4.0 → 0.5.0（新增公开方法，非破坏性）。
