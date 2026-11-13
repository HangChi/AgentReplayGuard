---
description: "Task list for 009 stream body loss"
---

# Tasks: 流式响应体丢失语义（httpx 传输层）

**Input**: Design documents from `/specs/009-stream-body-loss/`

**Tests**: 测试先行是强制要求（宪法第 IV 条）。

---

## Phase 0: 前置与基线（Setup）

- [x] T001 `pyproject.toml` 版本 bump 到 0.9.0
- [x] T002 运行基线：`pytest -q`、`ruff check .`、`mypy src/agentreplayguard`、`coverage
  --fail-under=90`，记录全绿

---

## Phase 1: 同步流式 body 丢失 (Priority: P1) 🎯

- [x] T003 [P] 编写 `tests/unit/test_http_stream_body_loss.py`：FaultKind 含
  `STREAM_BODY_LOSS`；`is_before_commit(STREAM_BODY_LOSS)` 为 False；`FaultyTransport` 注入
  该故障后 `send`/`stream` 响应头正常、读 body 抛 `ReadError`；effect committed + fault；
  未分类请求透传不注入；其余五类故障不回归
- [x] T004 实现 `faults.py` 新增 `STREAM_BODY_LOSS` + `fault_exception` 分支
- [x] T005 实现 `guard.py` `_raise_if_after_commit` 对 STREAM_BODY_LOSS 记录后 return 不抛
- [x] T006 实现 `httpx.py` `FaultyTransport` body 包装（`_BrokenBodyStream`）

---

## Phase 2: 异步对称 + 重复检测 + 文档 (Priority: P1) 🎯

- [x] T007 [P] 扩展 `tests/unit/test_http_stream_body_loss.py`：`AsyncFaultyTransport` 注入后
  `aread()` 抛 `ReadError`；lost-ack 重试（无幂等键）`committed_count=2`、`ok=False`；幂等键
  折叠为 1
- [x] T008 实现 `AsyncFaultyTransport` 异步 body 包装（`_BrokenAsyncBodyStream`）
- [x] T009 [P] 更新 `docs/quickstart.md` + `README.md`：流式 body 丢失用法与能力清单

---

## Phase 3: 全量验证（Verification）

- [x] T010 全流程：`pytest tests examples`、`ruff check .`、`mypy src/agentreplayguard`、
  `coverage report --fail-under=90`，核对 001–008 无回归

---

## Notes

- **STREAM_BODY_LOSS 不抛异常**：语义是「副作用已提交 + 正常返回响应头 + body 读取失败」，
  故 guard 记录 committed 后 return，transport 层包装 body。
- **框架隔离**：核心 faults/guard 不 import httpx；body 包装只在 adapters/httpx.py。
- **无新依赖、无新字段**：复用 EffectRecord/FaultKind。
