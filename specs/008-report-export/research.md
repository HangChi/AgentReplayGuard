# Research: 报告结构化导出（to_dict / to_json）

**Feature**: 008-report-export
**Status**: Implemented

## R-01 为什么是「导出」而非「持久化 Effect Store」

**决策**：008 交付「报告结构化导出」，而非「持久化 Effect Store」。

**依据**：
1. 001 spec 第 199 行把「跨进程持久化、分布式 Effect Store」列为 Out of Scope，理由是
   「不是首版需求」（第 224 行）。重新评估后，这个判断仍成立：本工具定位是「单次 pytest
   测试运行内检测重复副作用」，跨测试用例共享账本是 pytest 反模式（测试应隔离）。
2. 真实需求是「**报告导出**」：CI 存档、事后审计、跨工具消费（如把失败报告喂给告警系统）。
   `ScenarioReport.format()` 目前只输出人类可读文本，无法被程序化消费。
3. `EffectRecord` 是 frozen dataclass，`dataclasses.asdict` 已能结构化（实测 17 个字段均可
   枚举），只需把 `status`/`fault` 等 Enum 转成 value 即可 JSON 序列化。

**被否决的方案**：实现 Effect Store 落盘/读回（文件或 SQLite）。理由：跨进程保留账本超出
「单次测试运行」定位（宪法第 VII 条 YAGNI）；且会引入存储后端依赖与一致性语义。

## R-02 导出格式

**决策**：`ScenarioReport.to_dict()` 返回纯 JSON 可序列化的 dict（Enum → value 字符串），
`to_json()` 返回紧凑 JSON 字符串；保持与 `format()` 一致的信息内容，且确定性输出（字段
顺序固定、无 wall clock）。

**依据**：`format()` 的确定性原则（宪法第 II 条）同样适用于导出——同一 seed 下 `to_json()`
必须逐字节一致。Enum 转 value（`str(EffectStatus.COMMITTED)` 已是 value，因为它是
`str, Enum`）天然确定。

## R-03 范围：只做导出，不碰存储

**决策**：导出是纯函数（report → dict/json），无 I/O、无依赖、无状态。

**依据**：符合宪法第 III 条（副作用只落本地）、第 V 条（小接口面，仅新增两个方法）、第 VII
条（YAGNI）。
