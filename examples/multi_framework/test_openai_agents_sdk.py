"""OpenAI Agents SDK scripted 工具流程示例：验证 guard 在真实框架工具管线下的记账。

依赖 `openai-agents`（可选），未安装时跳过。全程离线（ScriptedModel 不发真实 LLM 请求）。
"""

from __future__ import annotations

import asyncio

import pytest

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario

agents = pytest.importorskip("agents")
agents_testing = pytest.importorskip("agents.testing")

from agents import Agent, RunConfig, Runner, function_tool  # noqa: E402
from agents.testing import ScriptedModel, assistant_message, function_call  # noqa: E402


def test_scripted_tool_records_effect():
    scenario = Scenario("sdk-tool", seed=0, invariants=[NoDuplicateEffects("lookup")])
    guard = scenario.guard()

    @function_tool
    @guard.effect("lookup", key="order_id")
    def lookup_order(order_id: str) -> str:
        return f"order {order_id}"

    model = ScriptedModel(
        [
            [function_call("lookup_order", '{"order_id": "ORD-1"}', call_id="c1")],
            [assistant_message("delivered")],
        ]
    )
    agent = Agent(name="billing", tools=[lookup_order], model=model)

    async def run():
        result = await Runner.run(
            agent, "where is ORD-1", run_config=RunConfig(tracing_disabled=True)
        )
        return result

    result = asyncio.run(run())
    assert result.final_output == "delivered"
    assert len(scenario.effects.records) == 1
    assert scenario.effects.records[0].business_key == "ORD-1"
    assert scenario.effects.records[0].status.value == "committed"


def test_scripted_tool_injects_fault():
    scenario = Scenario(
        "sdk-fault",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="lookup", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("lookup")],
    )
    guard = scenario.guard()

    @function_tool
    @guard.effect("lookup", key="order_id")
    def lookup_order(order_id: str) -> str:
        return f"order {order_id}"

    model = ScriptedModel(
        [
            [function_call("lookup_order", '{"order_id": "ORD-1"}', call_id="c1")],
            [assistant_message("done")],
        ]
    )
    agent = Agent(name="billing", tools=[lookup_order], model=model)

    asyncio.run(
        Runner.run(agent, "x", run_config=RunConfig(tracing_disabled=True))
    )

    record = scenario.effects.records[0]
    assert record.status.value == "not_committed"
    assert record.fault is FaultKind.TIMEOUT_BEFORE_COMMIT
