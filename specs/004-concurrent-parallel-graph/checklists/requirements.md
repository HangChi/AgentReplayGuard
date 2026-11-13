# Requirements Checklist: 并发与并行图副作用竞态检测

**Feature**: 004-concurrent-parallel-graph

## 规格核对

- [x] 用户故事按优先级排序（US1 P1 → US2 P1 → US3 P3），每个可独立测试
- [x] 边界题型单独成故事（US3 异步交错并发为独立进阶故事）
- [x] 「明确不含」表每项给依据（多进程并发=宪法 II；完整线性化=R-04；流式/框架/客户端=独立特性；真实服务/遥测/Web UI/自动修复=宪法 III/隐私/VII）
- [x] Success Criteria 可判定（SC-001 确定性 20/20、SC-002/003 去重口径、SC-004 覆盖率、SC-007 回归）

## 功能需求核对

- [x] FR-001 fan-out 识别并允许运行
- [x] FR-002 get_config 节点名作为 branch_id + 可注入 resolver
- [x] FR-003 EffectRecord.branch_id 扩展字段
- [x] FR-004 NoDuplicateEffects 报告分支归属
- [x] FR-005 并发判定机制（区间重叠）
- [x] FR-006 报告含 branch_id 且确定性
- [x] FR-007 核心模块不 import LangGraph（经可注入 resolver 隔离）
- [x] FR-008 strict_graph 语义明确化
- [x] FR-009 同步/异步检测结论与归属一致
- [x] FR-010 串行图无回归
- [x] FR-011 InvalidUpdateError 原样传播

## 与宪法的对齐核对

| 宪法原则 | 是否对齐 | 说明 |
|----------|----------|------|
| I. 真实需求优先 | ✅ | 竞品调研空白 + 并行是独立重复来源 |
| II. 确定性可复现 | ✅ | 检测结论与 branch 归属确定；真并发下追加顺序抖动已标注 |
| III. 默认模拟外部服务 | ✅ | 全进程内模拟 |
| IV. 测试先行 | ✅ | 失败测试先行 |
| V. 小接口面 | ✅ | 仅扩展 1 字段 + 1 不变量 |
| VI. 模块化边界 | ✅ | 可注入 resolver，核心不 import 框架 |
| VII. 克制范围 | ✅ | 明确 YAGNI 边界 |
| VIII. 失败可解释 | ✅ | branch_id 定位分支来源 |

## Notes

- **实测推翻的假设（实现阶段再次修正）**：research R-03 初稿认为「LangGraph fan-out 是顺序
  调度、确定可复现」，实现阶段实测发现同步 fan-out 是**线程池真并发**（节点 b/c 不同线程、
  交错执行），effect 追加 `sequence` 顺序抖动。但**检测结论不依赖追加顺序**（去重/计数/区间
  重叠均排序或集合判定），故确定性承诺收缩为「branch 归属 + 检测结论确定」，追加顺序标注
  为不确定（宪法第 II 条「并发调度 MUST 标注」）。
- **branch_id 来源修正**：初稿用 contextvar 注入，实测发现 contextvar 父值会被线程池子线程
  继承、无法区分分支；改为 `get_config()['metadata']['langgraph_node']`，经可注入 resolver 隔离
  框架依赖（宪法第 V 条）。
- **范围修正**：初稿把「真线程并发」列为 Out of Scope，但同步 fan-out 本身就是线程池并发，
  予以支持；仅「多进程并发」仍 Out of Scope。
