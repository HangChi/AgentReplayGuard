"""US2 独立验收：幂等键消除重复退款；错误实现（每次重试不同键）被检测。"""

from __future__ import annotations

from .graph import build_graph
from .tools import make_tools


def test_idempotent_single_refund(lost_ack_scenario, retry_policy):
    refund, notify, service = make_tools(lost_ack_scenario)
    graph = build_graph(
        refund,
        notify,
        retry_policy=retry_policy,
        idempotency_key_factory=lambda state: f"idem-{state['refund_id']}",
    )

    graph.invoke({"refund_id": "R-1", "amount_cents": 100})

    report = lost_ack_scenario.finish()
    assert report.ok
    assert service.count() == 1
    assert lost_ack_scenario.effects.committed_count("refund") == 1


def test_varying_key_detected(lost_ack_scenario, retry_policy):
    refund, notify, service = make_tools(lost_ack_scenario)
    calls: dict[str, int] = {"n": 0}

    def varying_key(state: dict) -> str:
        calls["n"] += 1
        return f"idem-{calls['n']}"

    graph = build_graph(
        refund,
        notify,
        retry_policy=retry_policy,
        idempotency_key_factory=varying_key,
    )

    graph.invoke({"refund_id": "R-1", "amount_cents": 100})

    report = lost_ack_scenario.finish()
    assert not report.ok
    assert service.count() == 2
    assert lost_ack_scenario.effects.committed_count("refund") == 2
