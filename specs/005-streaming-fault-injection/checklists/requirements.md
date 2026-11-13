# Requirements Checklist: 流式接口副作用归属与故障注入

**Feature**: 005-streaming-fault-injection

## 规格核对

- [x] 用户故事按优先级排序（US1 P1 → US2 P1 → US3 P2），每个可独立测试
- [x] 边界题型单独成故事（US3 astream_events 独立）
- [x] 「明确不含」表每项给依据（同步 stream=可后续补、流式响应体=003 扩展、token 断言=用户自断言、其他框架/客户端/持久化=独立特性）
- [x] Success Criteria 可判定（SC-001~SC-004 归属/结论等价、SC-005 覆盖率、SC-006 回归）

## 功能需求核对

- [x] FR-001 astream 入口 + 参数透传
- [x] FR-002 astream_events 入口 + 参数透传
- [x] FR-003 生成器周围 _begin_run/_finish_run
- [x] FR-004 effect 正确归属 run/thread/checkpoint/branch
- [x] FR-005 缺异步能力抛 UnsupportedGraphError
- [x] FR-006 故障注入/重试/不变量与 ainvoke 等价
- [x] FR-007 中途异常正确收尾 + 原样抛出
- [x] FR-008 提前退出正确收尾
- [x] FR-009 报告确定性
- [x] FR-010 既有入口无回归

## 与宪法的对齐核对

| 宪法原则 | 是否对齐 | 说明 |
|----------|----------|------|
| I. 真实需求优先 | ✅ | 实测无归属 + 竞品空白 |
| II. 确定性可复现 | ✅ | 复用 seed/逻辑时钟/分支归属 |
| III. 默认模拟外部服务 | ✅ | 全进程内模拟 |
| IV. 测试先行 | ✅ | 失败测试先行 |
| V. 小接口面 | ✅ | 仅新增 2 方法 |
| VI. 模块化边界 | ✅ | 改动只在 adapters/langgraph.py |
| VII. 克制范围 | ✅ | 明确 YAGNI 边界 |
| VIII. 失败可解释 | ✅ | 补齐 run/branch 归属 |

## Notes

- **实测事实**：绕过适配器直接 `graph.astream()` 时 effect 能记账但 `run_id`/`branch_id` 为
  `None`（research R-02），这是本特性的直接动机。
- **实测事实**：流式下故障注入 + retry + `NoDuplicateEffects` 与 ainvoke 完全等价（R-03），
  故本特性只需补「归属层」，不重做检测逻辑。
- **约束**：流式入口是异步生成器，归属用 `finally` 包裹保证所有退出路径（含 break）收尾。
