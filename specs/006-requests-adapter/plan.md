# Implementation Plan: requests 客户端的副作用记账与故障注入适配器

**Branch**: `006-requests-adapter` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-requests-adapter/spec.md`

## Summary

为 `requests` 提供与 003 httpx 对称的副作用记账与故障注入适配器。通过 `BaseAdapter` 子类 +
`Session.mount` 接缝，`send()` 对已分类请求调用 `scenario.guard().call` 完成 attempt 记账、
参数哈希与故障注入，把注入故障映射为 `requests.exceptions` 标准异常，使业务侧既有重试逻辑
原样生效。复用 `EffectGuard`/`EffectStore`/不变量，零新增核心依赖。

## Technical Context

**Language/Version**: Python ≥ 3.10

**Primary Dependencies**: 核心运行时仅标准库；新增可选 extra `requests>=2.28,<3.0`，仅在
`agentreplayguard.adapters.requests` 导入；`dev` extra 增加 requests。

**Storage**: 复用进程内 Effect Store，无新增存储。

**Testing**: pytest；用内存 mock adapter（自定义 `BaseAdapter` 返回预设 Response）离线运行，
无真实 socket。

**Target Platform**: Linux、macOS（Windows best-effort）

**Constraints**: 断网可运行；确定性；核心包导入不因缺 requests 失败；现有 API 不变；覆盖率 ≥90%

**Scale/Scope**: 抽取共享 `HttpEffect`（约 30 行）、新增 `adapters/requests.py`（约 100 行）、
2 个测试文件 + 1 个示例；不改 guard/fault 语义

## Constitution Check

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | requests 是 Python 最广泛 HTTP 客户端，003 仅覆盖 httpx；现有工具（responses/mock）不做副作用记账+故障注入+重复检测 |
| II. 确定性可复现 | PASS | 复用 seed 驱动的 FaultInjector 与逻辑时钟；内存 mock 无网络无延迟 |
| III. 默认模拟外部服务 | PASS | 测试用内存 mock adapter；不内置真实供应商客户端 |
| IV. 测试先行 | PASS | 先写失败测试再实现 |
| V. 小接口面与显式契约 | PASS | 新增 1 个 adapter 类；复用 HttpEffect；不改既有签名 |
| VI. 模块化与可替换边界 | PASS | 全部代码在 adapters/；核心模块不 import requests |
| VII. 克制范围（YAGNI） | PASS | 只做 requests 同步；不做 urllib3/aiohttp、流式响应体、自动重试推导 |
| VIII. 失败可解释 | PASS | 故障经既有账本记录，报告含 effect 类型/业务键/attempt/故障 |

**Gate result**: 全部通过。

## Project Structure

```
specs/006-requests-adapter/
├── spec.md / plan.md / research.md / data-model.md
├── contracts/requests-adapter.md
├── quickstart.md
├── checklists/requirements.md
└── tasks.md

src/agentreplayguard/adapters/
├── _http_common.py      # 新增：抽取共享 HttpEffect + 分类/映射辅助（不 import 任何 HTTP 库）
├── httpx.py             # 改为从 _http_common 导入 HttpEffect
└── requests.py          # 新增：RequestsAdapter
```

## 设计要点

### 1. 抽取共享 HttpEffect

`HttpEffect` 目前定义在 `adapters/httpx.py`（被 `import httpx` 包裹）。requests 要复用它但
不能连带 import httpx。方案：新建 `adapters/_http_common.py`，只依赖标准库，定义 `HttpEffect`、
`_classify_or_raise`（分类失败包装）、`_map_injected_fault` 骨架。httpx 与 requests 都从
`_http_common` 导入。httpx 的 `ClassifyRequest`（`Callable[[httpx.Request], ...]`）仍留在
httpx.py（类型别名因请求类型而异）。

### 2. requests 故障映射

`requests` 异常类 `ConnectTimeout`/`ReadTimeout`/`ConnectionError`/`HTTPError`/
`ChunkedEncodingError`，映射见 research R-02。`SERVER_ERROR` 用 `HTTPError` 携带 500 response；
`PARTIAL_SUCCESS` 用 `ChunkedEncodingError`。

### 3. 提交边界

与 httpx 一致：底层 `base.send()` 返回 response 即「已提交」。提交前故障（TIMEOUT_BEFORE_
COMMIT/CONNECTION_RESET/SERVER_ERROR）在调用 `base.send` 之前由 guard 注入；提交后故障
（TIMEOUT_AFTER_COMMIT/PARTIAL_SUCCESS）在 `base.send` 返回后由 guard 注入。

### 4. 复杂度跟踪

| 复杂度 | 说明 | 更简单方案为何被否决 |
|--------|------|----------------------|
| 抽取 `_http_common.py` | 共享 HttpEffect | 从 httpx.py 直接 import HttpEffect 会连带 import httpx（R-04），违反 requests 独立导入 |

## 阶段划分

1. **Phase 0 前置**：版本 bump 0.6.0，基线
2. **Phase 1 抽取共享**：`_http_common.py` + httpx 改造（无行为变化）
3. **Phase 2 US1/US2**：`RequestsAdapter` 记账 + 故障映射（测试先行）
4. **Phase 3 US3**：lost-ack 重复检测（测试先行）
5. **Phase 4 文档示例**：quickstart + examples + README
6. **Phase 5 全量验证**：pytest + ruff + mypy + coverage ≥90%
