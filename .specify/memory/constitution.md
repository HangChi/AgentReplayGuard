<!--
Sync Impact Report
==================
Version change: (none) → 1.0.0
Ratification: 初始版本，2026-11-12
Modified principles: N/A（首次创建）
Added sections:
  - Core Principles（7 条）
  - Additional Constraints（技术栈与安全边界）
  - Development Workflow（规格驱动与质量闸门）
  - Governance
Removed sections: N/A
Deferred TODOs: 无
-->

# AgentReplayGuard Constitution

## Core Principles

### I. 真实需求优先（Evidence Over Assumptions）

任何功能进入路线图前，MUST 能指向至少一类证据：可复现的故障案例、真实用户反馈、上游
Issue/文档，或明确的竞品能力缺口。MUST 在设计与文档中区分「已核实事实」「合理推断」
「待验证假设」，禁止把假设写成结论。MUST NOT 假设市场上没有竞品；立项与迭代前先做替代
方案调研，并说明为何现有工具不足。

理由：本项目是开发者工具，价值完全取决于是否解决真实存在的重复副作用问题；凭空设计的
功能只会增加维护成本。

### II. 确定性可复现（Reproducibility Is the Product）

同一场景、同一 seed、同一配置下，MUST 得到完全一致的执行轨迹与检测结论。故障注入
MUST 由固定 seed 驱动；时间、随机数、ID 生成 MUST 可注入；测试 MUST NOT 依赖真实网络、
真实时钟或外部服务。任何引入不确定性的设计（并发调度、真实延迟、系统时间）MUST 在
文档中标注，并提供可关闭的确定性路径。

理由：不可复现的测试工具没有诊断价值；用户需要的是「稳定复现一次线上事故」的能力。

### III. 默认模拟外部服务（Simulated by Default）

所有示例、测试与内置场景 MUST 只操作进程内模拟服务或本地存储；MUST NOT 调用真实支付、
退款、邮件、数据库等生产 API。项目 MUST NOT 内置任何真实供应商的写操作客户端。副作用
记录 MUST 只落在本地（内存或用户显式指定的文件/数据库），默认不上传、不联网。

理由：这是安全边界，也是用户敢在开发环境安装本工具的前提。

### IV. 测试先行（Test-First, NON-NEGOTIABLE）

每个模块 MUST 先写失败测试再实现（Red-Green-Refactor）。核心模块（Effect Store、Fault
Injector、Invariant Checker、LangGraph Adapter）MUST 达到 ≥90% 行覆盖率；每个公开
API MUST 至少有一个正向用例和一个失败/边界用例。修复 bug 时 MUST 先补回归测试。

理由：本项目本身就是测试工具，若自身测试不可信，产品承诺不成立。

### V. 小接口面与显式契约（Minimal Public API）

公开 Python API MUST 保持最小且语义明确：一个 pytest 入口、一个场景配置对象、一组
effect 记录查询与断言接口。公开 API 变更 MUST 遵循 SemVer；破坏性变更 MUST 提供迁移
说明。内部实现细节 MUST NOT 出现在公开签名中。上游易变依赖（LangGraph）MUST 被隔离在
适配层之后，核心模块 MUST NOT import 框架代码。

理由：个人维护的开源项目无法承担大接口面的兼容成本；清晰契约也是用户信任的基础。

### VI. 模块化与可替换边界（Modular Boundaries）

系统 MUST 划分为独立可测的模块：Effect Store、Fault Injector、Simulated Service、
Invariant Checker、Framework Adapter。模块之间 MUST 通过明确的数据结构通信，MUST NOT
互相读取内部状态。新增框架支持（如其它 Agent 框架）MUST 以新增适配器实现，MUST NOT
修改核心模块语义。

理由：初期只支持 LangGraph，但问题本身与框架无关；边界清晰才能在不破坏核心的前提下扩展。

### VII. 克制范围（Simplicity / YAGNI）

MVP MUST 严格限制在已批准的范围（串行图、四类故障、三类不变量、单一示例）。新增功能
MUST 说明：解决什么证据支持的问题、为何现有范围不够、有哪些更简单的替代方案。MUST NOT
为假设中的未来需求预留抽象层、配置项或插件机制。代码重复优于过早抽象。

理由：独立开发者每周可投入时间有限，范围失控是开源项目失败的主要原因。

### VIII. 失败可解释（Explainable Failures）

当检测到重复副作用或不变量违规时，报告 MUST 包含：effect 类型、业务键、参数哈希、
第几次尝试、所属 run/thread/checkpoint、触发故障点，以及期望值 vs 实际值。MUST NOT
只输出「断言失败」而无可定位信息。

理由：用户使用本工具的目的不是知道「失败了」，而是知道「哪一步重复执行、为什么」。

## Additional Constraints

- **语言与版本**：Python ≥ 3.10；公开代码 MUST 提供类型注解并随包发布 `py.typed`。
- **依赖策略**：核心包运行时 MUST 仅依赖标准库；`langgraph` MUST 作为可选 extra
  （`pip install agentreplayguard[langgraph]`）。新增第三方依赖 MUST 在 PR 中说明必要性、
  维护状态与替代方案。
- **测试入口**：pytest 是唯一官方测试入口，MUST NOT 自带独立 runner。测试 MUST 在无网络
  环境下全部通过；CI 中 MUST 有联网禁用断言。
- **数据与隐私**：工具 MUST NOT 采集遥测，MUST NOT 默认持久化用户业务参数原文；示例数据
  MUST 为虚构数据。
- **平台**：MUST 支持 Linux 与 macOS；Windows 为 best-effort，不阻塞发布。

## Development Workflow

- **规格驱动开发**：每个特性 MUST 依次经过 speckit 流程：`specify` → `plan` → `tasks` →
  `implement`。实现前 MUST 存在已评审的 `spec.md` 与 `plan.md`；MUST NOT 跳过规格直接写
  产品代码。
- **阶段闸门**：每个阶段 MUST 明确任务、交付物、验收标准；上一阶段验收未通过 MUST NOT
  进入下一阶段。
- **质量闸门**：合并前 MUST 通过 ruff 检查、pytest 全量测试、核心覆盖率 ≥90%；文档与
  可运行示例 MUST 随功能一起交付（Definition of Done 的一部分）。
- **提交规范**：使用 Conventional Commits（`feat:`、`fix:`、`docs:`、`test:`、`chore:`）；
  一个提交 MUST 只做一件事。
- **决策记录**：影响公开 API、依赖、兼容范围的决策 MUST 在 `docs/` 或 `specs/` 中留下
  理由与替代方案说明，而非只存在于代码注释。

## Governance

本宪法优先于其它开发实践与个人偏好；当速度与原则冲突时，以原则为准。

- **修订流程**：任何修订 MUST 以文档形式说明动机、影响范围与迁移方案，经项目维护者确认
  后写入本文件，并同步更新版本号。
- **版本策略**：MAJOR 为原则删除或不兼容重定义；MINOR 为新增原则或实质性扩展；PATCH 为
  措辞澄清与非语义修正。
- **合规审查**：每次 PR/评审 MUST 核对是否违反本宪法；新增复杂度 MUST 被显式论证，否则
  拒绝。无法满足某条原则时 MUST 记录例外、理由与退出计划。
- **运行时指导**：功能级细节以 `specs/` 下的规格与计划为准，本宪法只约束不可协商的底线。

**Version**: 1.0.0 | **Ratified**: 2026-11-12 | **Last Amended**: 2026-11-12
