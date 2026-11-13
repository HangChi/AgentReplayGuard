"""退款示例：由异步节点组成的串行图。"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy, interrupt


def build_async_graph(refund, notify, *, retry_policy: RetryPolicy):
    async def do_refund(state):
        await refund(state["refund_id"], state["amount_cents"])
        return state

    async def do_notify(state):
        await notify(state["refund_id"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund, retry_policy=retry_policy)
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    return builder.compile()


def build_resume_graph(refund, notify):
    """带 checkpointer 的异步图，用于验证恢复语义。"""

    async def do_refund(state):
        await refund(state["refund_id"], state["amount_cents"])
        return state

    async def do_notify(state):
        await notify(state["refund_id"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.add_node("notify", do_notify)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "notify")
    builder.add_edge("notify", "__end__")
    return builder.compile(checkpointer=InMemorySaver())


def build_interrupt_graph(refund, *, effect_before_interrupt: bool):
    """在退款前后触发 interrupt 的异步图。"""

    async def do_refund(state):
        if effect_before_interrupt:
            await refund(state["refund_id"], state["amount_cents"])
            interrupt({"approval": "needed"})
        else:
            interrupt({"approval": "needed"})
            await refund(state["refund_id"], state["amount_cents"])
        return state

    builder = StateGraph(dict)
    builder.add_node("refund", do_refund)
    builder.set_entry_point("refund")
    builder.add_edge("refund", "__end__")
    return builder.compile(checkpointer=InMemorySaver())
