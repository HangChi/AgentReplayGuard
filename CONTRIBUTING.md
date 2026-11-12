# Contributing to AgentReplayGuard

感谢你考虑贡献。本项目采用规格驱动的开发流程（spec-kit），并遵循项目宪法
[`.specify/memory/constitution.md`](.specify/memory/constitution.md) 中的原则。

## 开发流程

每个功能必须依次经过 speckit 流程：`specify` → `plan` → `tasks` → `implement`。在编写
产品代码之前，必须先存在已评审的 `spec.md` 与 `plan.md`。

## 环境准备

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,langgraph]"
```

## 质量闸门

合并前必须全部通过：

```bash
ruff check .
mypy src/agentreplayguard
pytest --cov=agentreplayguard --cov-report=term-missing
```

核心模块（Effect Store、Fault Injector、Invariant Checker、LangGraph Adapter）行覆盖率
不得低于 90%。

## 测试先行

每个模块先写失败测试，再实现（Red-Green-Refactor）。修复 bug 前先补回归测试。

## 提交规范

使用 Conventional Commits（`feat:`、`fix:`、`docs:`、`test:`、`chore:`）。一个提交只做
一件事。

## 关键约束

- 所有故障测试默认使用模拟外部服务，不调用真实支付或生产 API。
- 核心包运行时仅依赖标准库；`langgraph` 是可选 extra。
- 测试必须在无网络环境下通过。
- 新增第三方依赖需在 PR 中说明必要性、维护状态与替代方案。
