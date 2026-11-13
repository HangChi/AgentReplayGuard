# Implementation Plan: HTTP 故障注入传输层

**Branch**: `003-http-fault-transport` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-http-fault-transport/spec.md`

## Summary

在不改写业务代码的前提下，为真实 HTTP 客户端提供传输层适配器：同步 `FaultyTransport` 与
异步 `AsyncFaultyTransport` 包裹任意底层 transport，通过用户声明的分类函数把请求映射为
effect 语义，再复用现有 `EffectGuard.call/acall` 完成 attempt 记账、参数哈希与故障注入。
注入故障按故障阶段转换为客户端库的标准异常（提交前连接类、提交后读取类），使业务侧既有
重试逻辑原样生效。`httpx` 作为可选 extra 隔离在 `adapters/httpx.py`，核心包仍仅标准库；
测试使用 `httpx.MockTransport` 在进程内离线运行。

## Technical Context

**Language/Version**: Python ≥ 3.10（CI 覆盖 3.10–3.13）

**Primary Dependencies**: 核心运行时仅标准库；新增可选 extra `httpx>=0.27,<1.0`，仅在
`agentreplayguard.adapters.httpx` 导入；`dev` extra 增加 httpx 以便测试与示例

**Storage**: 复用进程内 Effect Store，无新增存储与持久化

**Testing**: pytest；同步与异步测试均使用标准库 `asyncio.run` 驱动，不引入 pytest-asyncio；
HTTP 层使用 `httpx.MockTransport`，无真实 socket

**Target Platform**: Linux、macOS（Windows best-effort）

**Project Type**: 单包 Python 库（pytest 插件形态）

**Performance Goals**: 单个典型 HTTP 场景 <5 秒；无真实网络与真实延迟

**Constraints**: 断网可运行；确定性（seed/逻辑时钟驱动）；核心包导入不得因缺少 httpx 失败；
现有公开 API 与报告结构不变；覆盖率 ≥90%

**Scale/Scope**: 新增 1 个适配模块（约 180 行）、2 个测试文件、1 个示例文件；不引入新的
核心依赖、不改变 guard/fault 语义

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | 证据：真实 Agent 写副作用多经 HTTP 客户端；函数级包装要求逐点改写，传输层是既有生态提供的稳定接缝 |
| II. 确定性可复现 | PASS | 复用 seed 驱动的 FaultInjector 与逻辑时钟；MockTransport 无网络、无延迟、无并发调度 |
| III. 默认模拟外部服务 | PASS | 示例与测试仅使用进程内 MockTransport；不内置任何真实供应商客户端 |
| IV. 测试先行 | PASS | 先写同步/异步适配器失败测试，再实现；新增模块纳入覆盖率统计 |
| V. 小接口面与显式契约 | PASS | 新增 1 个数据类、1 个分类回调类型、2 个 transport 类；不改现有签名；契约文档化 |
| VI. 模块化与可替换边界 | PASS | 全部代码位于 `adapters/httpx.py`；核心模块不 import httpx；通过 Scenario/Guard 既有接口通信 |
| VII. 克制范围（YAGNI） | PASS | 只做 httpx 同步/异步；不做流式语义、其他客户端、并发与自动重试推断 |
| VIII. 失败可解释 | PASS | 故障经既有账本记录，报告仍包含 effect 类型、业务键、attempt、fault 与归属信息 |

**Gate result**: 全部通过，无需例外说明。

## Project Structure

### Documentation (this feature)

```text
specs/003-http-fault-transport/
├── plan.md              # 本文件
├── research.md          # Phase 0：技术决策与替代方案
├── data-model.md        # Phase 1：HttpEffect 与故障映射
├── quickstart.md        # Phase 1：验收步骤
├── contracts/
│   └── http-transport-api.md  # Phase 1：公开 API 契约
├── checklists/
│   └── requirements.md  # 规格质量检查表
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成）
```

### Source Code (repository root)

```text
src/agentreplayguard/
├── __init__.py                  # 不变：不导入 httpx 适配器
├── adapters/
│   ├── __init__.py              # 不变
│   ├── langgraph.py             # 不变
│   └── httpx.py                 # 新增：HttpEffect / FaultyTransport / AsyncFaultyTransport
├── effects.py                   # 复用：读取记录以判定故障阶段
├── faults.py                    # 复用：FaultKind / 阈值映射输入
├── guard.py                     # 复用：call / acall
└── scenario.py                  # 复用：guard() 与 effects

tests/
├── unit/
│   ├── test_http_transport.py        # 新增：同步记账、透传、故障映射、配置错误
│   └── test_http_transport_async.py  # 新增：异步记账、取消、同步等价
└── contract/
    └── test_http_public_api.py       # 新增：可选依赖隔离与公开签名

examples/refund/
├── http_tools.py                # 新增：MockTransport 退款服务 + 分类函数
└── test_refund_http.py          # 新增：同步/异步 lost-ack 与幂等示例

docs/quickstart.md               # 增加 HTTP 传输层用法
README.md                        # 更新能力说明
pyproject.toml                   # 新增 httpx extra、dev 依赖、版本 0.3.0
```

**Structure Decision**: 沿用单包 `src/` 布局；HTTP 能力作为 `adapters` 下的新适配器，
与 LangGraph 适配器同级，核心模块不感知 httpx。

## Complexity Tracking

无违反项，无需填写。

## Post-Design Constitution Re-Check

| 原则 | 结论 | 设计后说明 |
|------|------|------------|
| I / II / III | PASS | 设计只增加传输层接缝，模拟边界、确定性与证据链不变 |
| IV | PASS | 测试覆盖透传、记账、五类故障映射、分类错误、取消与同步等价 |
| V | PASS | 公开面仅 `HttpEffect`、`FaultyTransport`、`AsyncFaultyTransport` 与分类回调 |
| VI / VII | PASS | 单个适配模块；明确排除流式、其他客户端与并发；核心零新依赖 |
| VIII | PASS | 失败仍落到既有 Effect Store 与 ScenarioReport，定位信息完整 |
