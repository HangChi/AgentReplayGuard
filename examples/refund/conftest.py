"""退款示例的共享 fixture。"""

from __future__ import annotations

import pytest
from langgraph.types import RetryPolicy

from agentreplayguard import (
    FaultKind,
    FaultPlan,
    FaultRule,
    NoDuplicateEffects,
    Scenario,
    ServiceError,
)


@pytest.fixture
def lost_ack_scenario() -> Scenario:
    """复现「提交后超时」导致的重复退款场景。"""
    return Scenario(
        "refund-lost-ack",
        seed=0,
        faults=FaultPlan(
            [FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1)]
        ),
        invariants=[NoDuplicateEffects("refund")],
    )


@pytest.fixture
def retry_policy() -> RetryPolicy:
    """对瞬态故障（超时/连接重置/5xx）进行重试。"""
    return RetryPolicy(
        max_attempts=3,
        retry_on=(TimeoutError, ConnectionError, ServiceError),
        initial_interval=0,
        jitter=False,
    )
