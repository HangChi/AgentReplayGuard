# Implementation Plan: 流式响应体丢失语义（httpx 传输层）

**Branch**: `009-stream-body-loss` | **Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-stream-body-loss/spec.md`

## Summary

新增 `FaultKind.STREAM_BODY_LOSS`，让 httpx 传输层能注入「响应头正常到达、body 读取时抛
`ReadError`」的故障。区别于其它提交后故障（guard 抛异常），`STREAM_BODY_LOSS` 的语义是
「副作用已提交，正常返回响应头，但 body 流读取时失败」，因此 guard 的 `_raise_if_after_commit`
对它在记录 `committed + fault` 后**不抛异常**、正常返回 result；transport 层在 `guard.call`
返回后检查 effect 记录的 fault，若为 `STREAM_BODY_LOSS` 则把响应体替换为会失败的流。

## Technical Context

**Language/Version**: Python ≥ 3.10

**Primary Dependencies**: 核心仅标准库；httpx 0.27–1.0 可选。

**Storage**: 复用进程内 Effect Store。

**Testing**: pytest；`httpx.MockTransport` 离线，无真实 socket。

**Constraints**: 确定性；核心包导入不因缺 httpx 失败；既有五类故障行为不变；覆盖率 ≥90%

**Scale/Scope**: `faults.py` 加 1 枚举值 + 1 分支；`guard.py` 改 1 方法（3 行）；`httpx.py`
加 body 包装流（同步+异步）；2 个测试文件

## Constitution Check

| 原则 | 结论 | 说明 |
|------|------|------|
| I. 真实需求优先 | PASS | 003 明确列为 Out of Scope（第 122/182 行），实测注入机制可行（R-02） |
| II. 确定性可复现 | PASS | 复用 seed 驱动 FaultInjector；body 流失败是确定性注入 |
| III. 默认模拟外部服务 | PASS | MockTransport 离线 |
| IV. 测试先行 | PASS | 先写失败测试 |
| V. 小接口面与显式契约 | PASS | 新增 1 枚举值，不改公开签名 |
| VI. 模块化与可替换边界 | PASS | 只改 faults/guard/httpx 适配器 |
| VII. 克制范围（YAGNI） | PASS | 只做 httpx，requests 流式不做（R-04） |
| VIII. 失败可解释 | PASS | effect 记 committed + fault=stream_body_loss，报告可区分故障点 |

**Gate result**: 全部通过。

## 设计要点

### 1. STREAM_BODY_LOSS 是「提交后、不抛异常」的故障

`is_before_commit(STREAM_BODY_LOSS)` 为 False（提交后）。`guard._raise_if_after_commit` 对它在
`_record_outcome(COMMITTED, fault=...)` 后**直接 return**，不抛 `fault_exception`。这样
`guard.call` 正常返回 `result`（Response），effect 已记 committed + fault。

### 2. transport 层包装 body

`FaultyTransport.handle_request` 在 `guard.call` 返回后，用 `_new_record(scenario, records_before)`
取刚记录的 effect，若 `fault is STREAM_BODY_LOSS`，则用「会失败的字节流」替换响应体：

```python
class _BrokenBodyStream(httpx.SyncByteStream):
    def __iter__(self):
        yield b""
        raise httpx.ReadError("stream body lost after headers")


resp = httpx.Response(
    status_code=resp.status_code,
    headers=resp.headers,
    content=_BrokenBodyStream(),
    request=request,
)
```

异步对称，用 `httpx.AsyncByteStream`（实现 `__aiter__`）。

### 3. fault_exception 兜底

`fault_exception(STREAM_BODY_LOSS)` 返回 `PartialSuccessError("stream body loss")` 作为语义
兜底（正常流程不经过它，但保持枚举完整性）。

## 阶段划分

1. **Phase 0 前置**：版本 bump 0.9.0，基线
2. **Phase 1**：FaultKind + guard 不抛异常 + transport 包装（测试先行）
3. **Phase 2**：异步对称 + 文档 + 全量验证
