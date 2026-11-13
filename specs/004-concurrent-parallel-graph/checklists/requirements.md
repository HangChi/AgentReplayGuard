# Requirements Checklist: 并发与并行图副作用竞态检测

**Feature**: 004-concurrent-parallel-graph

## 规格核对

- [x] 用户故事按优先级排序（US1 P1 → US2 P1 → US3 P3），每个可独立测试
- [x] 边界题型单独成故事（US3 异步交错并发为独立进阶故事）
- [x] 「明确不含」表每项给依据（真线程/多进程=宪法 II；完整线性化=R-04；流式/框架/客户端=独立特性；真实服务/遥测/Web UI/自动修复=宪法 III/隐私/VII）
- [x] Success Criteria 可判定（SC-001 确定性 20/20、SC-002/003 去重口径、SC-004 覆盖率、SC-007 回归）

## 功能需求核对

- [x] FR-001 fan-out 识别并允许运行
- [x] FR-002 确定性 branch_id + contextvar 注入
- [x] FR-003 EffectRecord.branch_id 扩展字段
- [x] FR-004 NoDuplicateEffects 报告分支归属
- [x] FR-005 并发判定机制（区间重叠）
- [x] FR-006 报告含 branch_id 且确定性
- [x] FR-007 核心模块不 import LangGraph
- [x] FR-008 strict_graph 语义明确化
- [x] FR-009 同步/异步归属一致
- [x] FR-010 串行图无回归
- [x] FR-011 InvalidUpdateError 原样传播

## 与宪法的对齐核对

| 宪法原则 | 是否对齐 | 说明 |
|----------|----------|------|
| I. 真实需求优先 | ✅ | 竞品调研空白 + 并行是独立重复来源 |
| II. 确定性可复现 | ✅ | 顺序调度实测 + 真并发 Out of Scope |
| III. 默认模拟外部服务 | ✅ | 全进程内模拟 |
| IV. 测试先行 | ✅ | 失败测试先行 |
| V. 小接口面 | ✅ | 仅扩展 1 字段 + 1 不变量 |
| VI. 模块化边界 | ✅ | contextvar 注入，核心不 import 框架 |
| VII. 克制范围 | ✅ | 明确 YAGNI 边界 |
| VIII. 失败可解释 | ✅ | branch_id 定位分支来源 |

## Notes

- **实测推翻的假设**：原 003 及更早文档假设「并行 fan-out 不可支持、遇之快速失败」，
  且隐含「并发天然不确定」。实测（research R-03）证明 LangGraph 1.2.20 的 fan-out 是
  顺序调度、确定可复现，故「支持 fan-out」不违反确定性原则。此差异已在 research 记录。
- **范围约束提醒**：真线程/多进程并发确不确定，故坚决排除，不因「并发」字样而扩大范围
  （宪法第 II、VII 条）。
