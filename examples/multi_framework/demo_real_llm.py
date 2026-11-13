"""真实 LLM 集成演示：验证 guard 在真实 OpenAI Agents SDK agent 下抓重复副作用。

⚠️ 这是「能力验证」而非「确定性测试」，不进 CI、不写死密钥。

用法：
    OPENAI_BASE_URL=https://token.ai-hf.cn/v1 \
    OPENAI_API_KEY=sk-xxx \
    OPENAI_MODEL=Deepseek-V4.1-Flash \
    python examples/multi_framework/demo_real_llm.py

未提供 OPENAI_API_KEY 时脚本直接退出（不报错）。
"""

# ruff: noqa: RUF001  # 中文输出使用全角标点
from __future__ import annotations

import asyncio
import os
import sys

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)


async def main() -> int:
    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model_name = os.environ.get("OPENAI_MODEL", "Deepseek-V4.1-Flash")

    if not api_key:
        print("未设置 OPENAI_API_KEY，跳过真实 LLM 演示。")
        return 0

    # 可选依赖：openai / openai-agents
    try:
        from agents import Agent, OpenAIResponsesModel, RunConfig, Runner, function_tool
        from openai import AsyncOpenAI
    except ImportError as exc:
        print(f"缺少依赖（pip install 'agentreplayguard[agents]'）：{exc}")
        return 1

    scenario = Scenario(
        "real-llm-demo",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()

    # 带 guard 的退款工具：第一次调用注入 lost-ack（提交后超时），业务侧重试
    @function_tool
    @guard.effect("refund", key="refund_id", idempotency_key="idempotency_key")
    def refund(refund_id: str, idempotency_key: str | None = None) -> str:
        return f"退款已提交：{refund_id}"

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    model = OpenAIResponsesModel(model=model_name, openai_client=client)
    agent = Agent(
        name="退款助手",
        instructions="用户要求退款时必须调用 refund 工具，refund_id 用订单号，"
        "idempotency_key 用同一订单号。只调用一次 refund 工具。",
        tools=[refund],
        model=model,
    )

    try:
        await Runner.run(
            agent,
            "请给订单 ORD-REAL-1 退款",
            run_config=RunConfig(tracing_disabled=True),
        )
    except Exception as exc:  # 演示：故障可能中断 agent
        print(f"agent 运行异常（可能是注入的 lost-ack）：{type(exc).__name__}")

    report = scenario.finish()
    print("=== 演示报告 ===")
    print(report.format())

    # 成功判据：effect 记账 + 故障注入（确定性），而非「必现重复」（真实 LLM 下概率性）
    records = scenario.effects.for_effect("refund")
    if not records:
        print("\n失败：agent 未调用退款工具（真实 LLM 行为不可复现，可重试或换模型）")
        return 1
    injected = any(r.fault is not None for r in records)
    print(f"\neffect 记账 {'成功' if records else '失败'}")
    print(f"故障注入 {'成功' if injected else '未注入'}")
    if report.ok:
        print("（本次 agent 未重复调用，未触发 NoDuplicateEffects——真实 LLM 下这是正常的；"
              "确定性重复检测请用 test_openai_agents_sdk.py 的 ScriptedModel）")
    else:
        print("重复副作用已检测到 ✓")
    return 0 if records else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
