# Requirements Checklist: 多框架工具副作用记账

**Feature**: 007-multi-framework-tools

## 规格核对

- [x] 用户故事按优先级排序（US1 P1 → US2 P1 → US3 P2），每个可独立测试
- [x] 「明确不含」表每项给依据（完整适配器=R-01/R-05、handoff/guardrail=框架运行时、真实 LLM=宪法 III）
- [x] Success Criteria 可判定（SC-001~SC-005）

## 功能需求核对

- [x] FR-001 复用 guard.effect，无新增框架运行时逻辑
- [x] FR-002 多框架接入文档 + 装饰器顺序
- [x] FR-003 OpenAI Agents SDK scripted 示例
- [x] FR-004 CrewAI/AutoGen 接入说明
- [x] FR-005 全部离线无真实 LLM
- [x] FR-006 既有行为不变

## 与宪法的对齐核对

| 宪法原则 | 是否对齐 | 说明 |
|----------|----------|------|
| I. 真实需求优先 | ✅ | 三框架广泛使用 + 工具函数接缝 |
| II. 确定性可复现 | ✅ | ScriptedModel + guard.effect |
| III. 默认模拟外部服务 | ✅ | 离线 scripted |
| IV. 测试先行 | ✅ | 工具函数级测试先行 |
| V. 小接口面 | ✅ | 无新 API |
| VI. 模块化边界 | ✅ | 工具函数天然边界 |
| VII. 克制范围 | ✅ | 不做完整适配器 |
| VIII. 失败可解释 | ✅ | 复用账本报告 |

## Notes

- **关键决策**：007 不写完整框架适配器，而是文档化「用 guard.effect 装饰工具函数」。这是
  research R-01 的核心结论——副作用拦截点在工具函数本身，完整适配器是过度设计（YAGNI）。
- **可选依赖**：`openai-agents` 仅示例用，用 `pytest.importorskip` 守卫，不进 dev extra。
