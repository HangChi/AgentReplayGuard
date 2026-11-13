"""并行退款 LangGraph 图：一个 fan-out，两个分支各自尝试退款同一订单。

演示并行分支重复副作用：无幂等键时两个分支各提交一次退款，被 NoDuplicateEffects 检测；
带相同幂等键时正确折叠为一次。
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph


class ParallelState(TypedDict):
    refund_id: str
    amount_cents: int
    log: Annotated[list[str], operator.add]


def build_parallel_graph(
    refund: Callable[..., Any],
    *,
    idempotency_key_factory: Callable[[dict], str | None] | None = None,
):
    """构建一个 fan-out 图：start → (refund_a, refund_b) → END。

    两个分支都调用 refund，模拟「并行任务各自触发退款」的缺陷场景。
    """

    builder = StateGraph(ParallelState)

    def start(state: ParallelState) -> dict:
        return {"log": ["start"]}

    def refund_a(state: ParallelState) -> dict:
        ik = idempotency_key_factory(state) if idempotency_key_factory else None
        refund(state["refund_id"], state["amount_cents"], ik)
        return {"log": ["refund_a"]}

    def refund_b(state: ParallelState) -> dict:
        ik = idempotency_key_factory(state) if idempotency_key_factory else None
        refund(state["refund_id"], state["amount_cents"], ik)
        return {"log": ["refund_b"]}

    builder.add_node("start", start)
    builder.add_node("refund_a", refund_a)
    builder.add_node("refund_b", refund_b)
    builder.add_edge(START, "start")
    builder.add_edge("start", "refund_a")
    builder.add_edge("start", "refund_b")  # fan-out
    builder.add_edge("refund_a", END)
    builder.add_edge("refund_b", END)
    return builder.compile()
