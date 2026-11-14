# Research: 多框架工具副作用记账（OpenAI Agents SDK / CrewAI / AutoGen）

**Feature**: 007-multi-framework-tools
**Status**: Implemented

## R-01 核心判断：工具函数是纯 Python 函数，可直接用 guard.effect 装饰

**决策**：007 不写「完整框架适配器」（如 LangGraphAdapter 那样驱动整图），而是验证并文档化
「用现有 `guard.effect()` 装饰各框架的工具函数」即可完成副作用记账 + 故障注入 + 重复检测。

**依据**：本工具的核心能力（attempt 记账、参数哈希、五类故障注入、`NoDuplicateEffects` 等
不变量）全部作用于「副作用函数被调用的那一刻」，与框架无关。LangGraph 需要专门适配器，是
因为它的副作用发生在「图节点内部」且需要 run/checkpoint/branch 归属；而 OpenAI Agents SDK
的 `@tool`、CrewAI 的 `@tool`、AutoGen 的工具函数**本质都是普通 Python callable**，用
`guard.effect()` 包裹即可复用全部现有能力，无需理解框架运行时。

**被否决的方案**：为每个框架写完整适配器（驱动 agent loop）。理由：① 副作用拦截点就在工具
函数本身，完整适配器是过度设计（宪法第 VII 条 YAGNI）；② 三个框架都依赖真实 LLM API，
完整适配器会违反宪法第 III 条「默认模拟外部服务」；③ 维护成本与价值不匹配。

## R-02 OpenAI Agents SDK：官方 ScriptedModel 支持离线确定性测试

**决策**：OpenAI Agents SDK 是三者中「离线确定性测试」最成熟的框架，作为 007 的首个验证目标。

**依据**：官方 `agents.testing.ScriptedModel` 运行在内存、不发任何模型/沙箱/Realtime 请求，
记录 SDK 拥有的交互；`RunConfig(tracing_disabled=True)` 保证完全离线。`@tool` 装饰的工具
在 scripted run 中走**真实的 SDK 工具管线**（`function_call` → 工具执行 → 结果回传），
这正好是副作用发生的地方，可用 `guard.effect()` 装饰工具验证记账与故障注入。

## R-03 CrewAI：工具可直接调用，Agent 级需 mock LLM

**决策**：CrewAI 工具函数可直接调用其 `run()` 接口（不经过 Agent/LLM），用 `guard.effect()`
装饰即可记账；Agent 级执行需 mock LLM（`unittest.mock` 替换 `llm`）。

**依据**：CrewAI 的 `@tool` 装饰对象暴露 `run` 接口，可脱离 Agent 直接调用（QABattle 指南
确认「A CrewAI tool can run without an agent」）。Agent 级测试需 mock LLM（LangChain
ChatModel 接口），且 CrewAI 0.30.0 后 API 有破坏性变更（`execute_task` 移除）。

## R-04 AutoGen（AG2）：无官方离线测试接缝

**决策**：AutoGen 无官方离线测试接缝，工具函数仍是纯 Python callable，用 `guard.effect()`
装饰即可；但不在 007 提供 Agent 级示例（缺乏官方 scripted 测试设施）。

**依据**：调研未发现 AutoGen 官方离线 scripted model 设施；其工具函数同样是普通 callable，
副作用拦截与框架无关。

## R-05 范围：007 = 工具函数装饰 + 文档 + 示例，不做完整适配器

**决策**：007 交付「工具函数级」的副作用安全测试支持（含 OpenAI Agents SDK 的 scripted 示例），
明确「不驱动整图/整 agent」的范围。

**依据**：这是宪法第 I 条（真实需求）与第 VII 条（克制范围）的平衡——副作用检测的接缝就在
工具函数，写完整适配器是浪费；但需要提供「如何把 guard 接入各框架工具」的文档与可运行示例，
否则用户不知如何使用。

## Sources

- [OpenAI Agents SDK Testing（ScriptedModel）](https://openai.github.io/openai-agents-python/testing)
- [CrewAI 工具离线测试](https://www.qabattle.com/blog/unit-test-crewai-tools-without-llm-calls)
- [CrewAI record/replay 需求（无官方离线设施）](https://gitmemories.com/index.php/crewAIInc/crewAI/issues/2759)
