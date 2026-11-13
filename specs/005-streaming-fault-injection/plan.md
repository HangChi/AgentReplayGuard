# Implementation Plan: 流式接口的副作用归属与故障注入

**Branch**: `005-streaming-fault-injection` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-streaming-fault-injection/spec.md`

## Summary

在 `LangGraphAdapter` 上新增 `astream` / `astream_events` 两个异步流式入口，让流式驱动图时
effect 也能正确归属 run / thread / checkpoint / branch。实现上复用既有 `_begin_run` /
`_finish_run` / `_ensure_async_capable` 逻辑，把归属「包」在异步生成器周围：生成器首次
迭代前 `_begin_run`，耗尽（正常/异常/中断/提前退出）时 `_finish_run`。effect 记账、故障
注入、重试、不变量检测全部通过节点内 `guard.call` 复用，不新增第二套逻辑，零新增依赖。

## Technical Context

**Language/Version**: Python ≥ 3.10（CI 覆盖 3.10–3.13）

**Primary Dependencies**: 核心运行时仅标准库；LangGraph 1.2.x 仍作为可选 extra 隔离在适配器层。

**Storage**: 复用进程内 Effect Store；无新增字段、无持久化。

**Testing**: pytest；流式测试用 `asyncio.run` 驱动 `async for`，不引入 pytest-asyncio。

**Target Platform**: Linux、macOS（Windows best-effort）

**Project Type**: 单包 Python 库（pytest 插件形态）

**Performance Goals**: 单个典型流式场景 <5 秒；无真实网络与真实延迟

**Constraints**: 断网可运行；确定性（seed/逻辑时钟/分支归属）；核心包导入不因缺 LangGraph
失败；现有公开 API 不变（仅新增两个方法）；覆盖率 ≥90%

**Scale/Scope**: 扩展 `adapters/langgraph.py`（约 60 行新增）、2 个测试文件 + 1 个示例；
不改 guard/fault/invariants 语义、不新增字段与依赖

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | 证据：实测「绕过适配器 astream 导致 effect 无归属」（research R-02）+ 竞品无流式副作用检测工具（R-06） |
| II. 确定性可复现 | PASS | 流式复用 seed 驱动的 FaultInjector 与逻辑时钟；归属逻辑与 ainvoke 一致；chunk/事件顺序由 LangGraph 决定，effect 归属确定 |
| III. 默认模拟外部服务 | PASS | 示例与测试仅进程内模拟；无真实供应商客户端 |
| IV. 测试先行 | PASS | 先写 astream/astream_events 失败测试，再实现 |
| V. 小接口面与显式契约 | PASS | 仅新增 `astream`/`astream_events` 两个方法，复用既有归属机制；不改既有签名 |
| VI. 模块化与可替换边界 | PASS | 全部改动在 `adapters/langgraph.py`；核心模块不 import LangGraph |
| VII. 克制范围（YAGNI） | PASS | 只做流式归属 + 故障注入等价；不做 token 级断言、同步 stream、流式响应体语义 |
| VIII. 失败可解释 | PASS | effect 归属补齐 run/branch，报告能定位「哪次 run、哪个分支」，修复无主记录 |

**Gate result**: 全部通过，无需例外说明。

## Project Structure

### Documentation (this feature)

```
specs/005-streaming-fault-injection/
├── spec.md              # 特性规格
├── plan.md              # 本文件
├── research.md          # 调研结论（R-01~R-06）
├── data-model.md        # 无新增结构（复用声明）
├── contracts/
│   └── streaming-entry.md   # 流式入口契约
├── quickstart.md        # 流式使用与验证步骤
├── checklists/
│   └── requirements.md  # 需求核对清单
└── tasks.md             # 实现任务清单
```

### Source Code (this feature)

```
src/agentreplayguard/adapters/langgraph.py   # 新增 astream / astream_events
```

## 设计要点

### 1. 流式归属：在异步生成器周围包 _begin_run / _finish_run

`ainvoke` 的归属流程（`checkpoint_before → _begin_run → graph.ainvoke → _extract_interrupts
→ _finish_run`）对一次性返回值有效；流式是逐 chunk 产出，需把 `_begin_run` 放到生成器首次
迭代前、`_finish_run` 放到生成器耗尽时。

实现骨架（伪代码）：

```python
async def astream(self, input, **kwargs):
    self._ensure_async_capable()
    checkpoint_before = self._checkpoint_id()
    run_id = self._scenario._begin_run(self._thread_id, checkpoint_before)
    started_tick = self._scenario._tick()
    exc = None
    try:
        async for chunk in self._graph.astream(input, self._config(), **kwargs):
            yield chunk
    except BaseException as caught:
        exc = caught
        raise
    finally:
        self._finish_run(run_id=run_id, input_kind=START, checkpoint_before=checkpoint_before,
                         started_tick=started_tick, output=None, interrupts=(), exc=exc)
```

关键点：
- `finally` 保证正常耗尽、异常、`break`（GeneratorExit）都执行 `_finish_run`。
- `output` 置 `None`（流式无单一最终返回值）；`interrupts` 需从流式中提取（见设计要点 2）。
- `astream_events` 结构相同，仅底层方法与透传参数不同。

### 2. 中断（interrupt）在流式下的提取

`ainvoke` 用 `_extract_interrupts(output)` 从返回值读 `__interrupt__`。流式无单一返回值，
需在遍历 chunk 时检测含 `__interrupt__` 的 chunk（LangGraph 的 interrupt 会以
`{'__interrupt__': [...]}` 形态出现在 chunk 流里）。方案：在遍历时累积 `interrupts`，传给
`_finish_run`。

### 3. 提前退出遍历的收尾

用户 `break` 退出 `async for` 会触发生成器的 `GeneratorExit`，`finally` 块仍执行
`_finish_run`，`exc` 为 `None`（正常收尾，`error_type=None`）。这保证不留半开 run。

### 4. 复杂度跟踪（Complexity Tracking）

| 复杂度 | 说明 | 更简单方案为何被否决 |
|--------|------|----------------------|
| 异步生成器 + finally 收尾 | 归属生命周期包裹 | 事后统一补记（R-05 否决）：需回写，破坏只追加语义 |
| 遍历时累积 interrupts | 中断提取 | 从流式 chunk 无法事后取到，必须遍历时捕获 |

## 阶段划分

1. **Phase 0 前置**：版本 bump 0.5.0，跑基线
2. **Phase 1 US1**：`astream` 入口 + effect 归属（测试先行）
3. **Phase 2 US2**：流式故障注入与重复检测等价（测试先行）
4. **Phase 3 US3**：`astream_events` 入口（测试先行）
5. **Phase 4 文档与示例**：quickstart + examples + README
6. **Phase 5 全量验证**：pytest + ruff + mypy + coverage ≥90%
