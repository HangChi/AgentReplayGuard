"""T043：LangGraph `RetryPolicy` 默认与显式 `retry_on` 行为。

验证两点：默认 `retry_on`（`default_retry_on`）对普通 `OSError` 不重试；
显式声明 `retry_on=(OSError,)` 后会被重试至 `max_attempts`。
"""

from __future__ import annotations

import pytest
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy


def _attempts_when_raising(retry_policy: RetryPolicy) -> int:
    calls: list[int] = []

    def flaky(state: dict) -> dict:
        calls.append(1)
        raise OSError("boom")

    builder = StateGraph(dict)
    builder.add_node("flaky", flaky, retry_policy=retry_policy)
    builder.set_entry_point("flaky")
    builder.add_edge("flaky", "__end__")
    graph = builder.compile()

    with pytest.raises(OSError):
        graph.invoke({})

    return len(calls)


def test_default_retry_on_does_not_retry_oserror():
    attempts = _attempts_when_raising(
        RetryPolicy(max_attempts=3, initial_interval=0, jitter=False)
    )
    assert attempts == 1


def test_explicit_retry_on_retries_oserror():
    attempts = _attempts_when_raising(
        RetryPolicy(max_attempts=3, retry_on=(OSError,), initial_interval=0, jitter=False)
    )
    assert attempts == 3
