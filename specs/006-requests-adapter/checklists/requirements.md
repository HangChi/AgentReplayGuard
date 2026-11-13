# Requirements Checklist: requests 适配器

**Feature**: 006-requests-adapter

## 规格核对

- [x] 用户故事按优先级排序（US1 P1 → US2 P1 → US3 P1），每个可独立测试
- [x] 「明确不含」表每项给依据（urllib3/aiohttp=R-03、流式响应体=独立、真实服务=宪法 III）
- [x] Success Criteria 可判定（SC-001~SC-005）

## 功能需求核对

- [x] FR-001 requests 可选依赖 + 可操作 ImportError
- [x] FR-002 RequestsAdapter + guard.call
- [x] FR-003 分类回调 + 复用 HttpEffect
- [x] FR-004 故障映射为 requests 异常
- [x] FR-005 close 委托 + 提交前不调 base
- [x] FR-006 复用 EffectGuard
- [x] FR-007 核心包导入不因缺 requests 失败
- [x] FR-008 现有 API 不变

## 与宪法的对齐核对

| 宪法原则 | 是否对齐 | 说明 |
|----------|----------|------|
| I. 真实需求优先 | ✅ | requests 生态空白 |
| II. 确定性可复现 | ✅ | 复用 seed + 内存 mock |
| III. 默认模拟外部服务 | ✅ | 内存 mock |
| IV. 测试先行 | ✅ | 失败测试先行 |
| V. 小接口面 | ✅ | 1 个类 |
| VI. 模块化边界 | ✅ | 核心不 import requests |
| VII. 克制范围 | ✅ | 只做 requests |
| VIII. 失败可解释 | ✅ | 复用账本报告 |

## Notes

- **抽取 HttpEffect**：为让 requests 复用 HttpEffect 而不 import httpx，抽取到共享
  `_http_common.py`（仅标准库）。这是本特性唯一的"结构调整"，无行为变化。
- **PARTIAL_SUCCESS 映射**：requests 无 `ReadError` 对应，用 `ChunkedEncodingError` 最接近
  「读取中断」，已在 research R-02 记录。
