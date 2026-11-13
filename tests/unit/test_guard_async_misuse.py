"""US4：同步入口误用异步工具必须立即失败且不污染账本。"""

from __future__ import annotations

import asyncio

import pytest

from agentreplayguard import Scenario, ScenarioConfigError


def test_sync_call_rejects_async_function_without_recording():
    scenario = Scenario("s")
    guard = scenario.guard()

    async def refund(refund_id):
        return refund_id

    with pytest.raises(ScenarioConfigError) as excinfo:
        guard.call("refund", refund, refund_id="R-1", key="refund_id")

    message = str(excinfo.value).lower()
    assert "acall" in message or "await" in message
    assert scenario.effects.records == ()
    assert scenario.effects.attempts("refund", "R-1") == 0


def test_sync_and_async_entries_share_attempt_counter():
    scenario = Scenario("s")
    guard = scenario.guard()

    def sync_refund(refund_id):
        return refund_id

    async def async_refund(refund_id):
        return refund_id

    guard.call("refund", sync_refund, refund_id="R-1", key="refund_id")
    asyncio.run(guard.acall("refund", async_refund, refund_id="R-1", key="refund_id"))

    assert [record.attempt for record in scenario.effects.records] == [1, 2]
