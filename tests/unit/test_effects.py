from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agentreplayguard import EffectStatus
from agentreplayguard.effects import EffectRecord, EffectStore


def test_status_enum_values():
    assert EffectStatus.COMMITTED.value == "committed"
    assert EffectStatus.NOT_COMMITTED.value == "not_committed"
    assert EffectStatus.UNKNOWN.value == "unknown"


def test_records_are_frozen(add_committed):
    record = add_committed(EffectStore(), "refund", "R-1")
    with pytest.raises(FrozenInstanceError):
        record.effect_type = "x"  # type: ignore[misc]


def test_store_queries(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    add_committed(store, "notify", "R-1")
    add_committed(store, "refund", "R-2")

    assert len(store.records) == 3
    assert len(store.for_effect("refund")) == 2
    assert len(store.for_key("refund", "R-1")) == 1
    assert store.for_key("refund", "missing") == ()


def test_committed_count_dedup_with_idempotency_key(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1", idem_hash="k1")
    add_committed(store, "refund", "R-1", idem_hash="k1")

    assert store.committed_count("refund") == 1
    assert len(store.records) == 2


def test_committed_count_no_idempotency_key_counts_each(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    add_committed(store, "refund", "R-1")

    assert store.committed_count("refund") == 2


def test_attempts_count():
    store = EffectStore()
    assert store.attempts("refund", "R-1") == 0
    store.next_attempt("refund", "R-1")
    store.next_attempt("refund", "R-1")
    assert store.attempts("refund", "R-1") == 2


def test_append_assigns_identity_and_sequence():
    store = EffectStore()
    record = EffectRecord(
        effect_id="",
        sequence=0,
        effect_type="refund",
        business_key="R-1",
        params_hash="h",
        idempotency_key_hash=None,
        attempt=1,
        status=EffectStatus.COMMITTED,
        fault=None,
        error_type=None,
        error_message=None,
        run_id=None,
        thread_id=None,
        checkpoint_id=None,
        started_tick=0,
        ended_tick=1,
    )
    stored = store.append(record)
    # 占位值被统一分配为真实 identity，且外部构造的 record 不被污染
    assert stored.effect_id == "eff-000001"
    assert stored.sequence == 1
    assert record.effect_id == ""
    assert record.sequence == 0

    stored2 = store.append(record)
    assert stored2.effect_id == "eff-000002"
    assert stored2.sequence == 2
    assert len(store.records) == 2


def test_append_records_are_visible_via_queries(add_committed):
    store = EffectStore()
    add_committed(store, "refund", "R-1")
    add_committed(store, "refund", "R-2")
    assert len(store.records) == 2
    assert len(store.for_effect("refund")) == 2
    assert len(store.for_key("refund", "R-1")) == 1
