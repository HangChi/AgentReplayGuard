"""US6 集成测试：确定性、断网运行与无真实 sleep。"""

from __future__ import annotations

import socket
import time

import pytest
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
)
from agentreplayguard.adapters.langgraph import LangGraphAdapter


def _run_refund(seed: int) -> tuple[int, bool, int]:
    """以给定 seed 跑一遍 lost-ack 场景，返回确定性指纹。"""
    scenario = Scenario(
        "determinism",
        seed=seed,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", probability=0.5)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str, amount_cents: int) -> str:
        return f"refunded {refund_id}"

    def do_refund(state: dict) -> dict:
        refund(state["refund_id"], state["amount_cents"])
        return state

    builder = StateGraph(dict)
    builder.add_node(
        "refund",
        do_refund,
        retry_policy=RetryPolicy(
            max_attempts=3,
            retry_on=(TimeoutError,),
            initial_interval=0,
            jitter=False,
        ),
    )
    builder.set_entry_point("refund")
    builder.add_edge("refund", "__end__")
    adapter = LangGraphAdapter(scenario, builder.compile())

    adapter.invoke({"refund_id": "R-1", "amount_cents": 100})
    report = scenario.finish()
    return (
        scenario.effects.committed_count("refund"),
        report.ok,
        len(report.violations),
    )


def test_same_seed_20_runs_identical():
    results = [_run_refund(seed=7) for _ in range(20)]
    assert len(set(results)) == 1


def test_different_seeds_diverge():
    results = {_run_refund(seed=s) for s in range(50)}
    assert len(results) > 1


def test_fault_injection_uses_logical_clock_not_real_sleep(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    scenario = Scenario(
        "no-sleep",
        seed=0,
        faults=FaultPlan([FaultRule(FaultKind.TIMEOUT_BEFORE_COMMIT, effect_type="refund")]),
    )
    guard = scenario.guard()

    @guard.effect("refund", key="refund_id")
    def refund(refund_id: str) -> str:
        return refund_id

    with pytest.raises(TimeoutError):
        refund("R-1")

    assert sleeps == []


def test_offline_run_makes_no_network_calls(monkeypatch):
    def _no_socket(*args, **kwargs):
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(socket, "socket", _no_socket)

    result = _run_refund(seed=7)
    assert result in {(2, False, 1), (1, True, 0)}
