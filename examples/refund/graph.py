"""退款 LangGraph 图：refund → notify 串行，refund 节点显式声明重试策略。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy


def build_graph(
    refund: Callable[..., Any],
    notify: Callable[..., Any],
    *,
    retry_policy: RetryPolicy | None = None,
    idempotency_key_factory: Callable[[dict], str] | None = None,
    checkpointer: Any | None = None,
):
    builder = StateGraph(dict)

    def do_refund(state: dict) -> dict:
        idempotency_key = idempotency_key_factory(state) if idempotency_key_factory else None
        refund(state["refund_id"], state["amount_cents"], idempotency_key)
        return dict(state)

    def do_notify(state: dict) -> dict:
        notify(state["refund_id"])
        return dict(state)

    if retry_policy is not None:
        builder.add_node("refund", do_refund, retry_policy=retry_policy)
    else:
        builder.add_node("refund", do_refund)
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()
