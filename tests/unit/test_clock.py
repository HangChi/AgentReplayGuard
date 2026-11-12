from __future__ import annotations

from agentreplayguard.clock import LogicalClock, counter_id


def test_clock_starts_at_zero_and_is_monotonic():
    clock = LogicalClock()
    assert clock.now() == 0
    first = clock.tick()
    second = clock.tick()
    assert first == 1
    assert second == 2
    assert clock.now() == 2
    assert first < second


def test_counter_id_format():
    assert counter_id("eff", 1, 6) == "eff-000001"
    assert counter_id("run", 1, 4) == "run-0001"
    assert counter_id("run", 12, 4) == "run-0012"


def test_counter_id_is_deterministic():
    assert counter_id("eff", 1, 6) == counter_id("eff", 1, 6)
