from __future__ import annotations

import pytest

from agentreplayguard import EffectStatus
from agentreplayguard.effects import EffectRecord, EffectStore


@pytest.fixture
def add_committed():
    """构建并追加一条 COMMITTED 记录，便于直接测试去重口径。"""

    def _add(
        store: EffectStore,
        effect_type: str,
        business_key: str,
        *,
        idem_hash: str | None = None,
        params_hash: str = "h",
        attempt: int = 1,
    ) -> EffectRecord:
        record = EffectRecord(
            effect_id=store._next_effect_id(),
            sequence=store._next_sequence(),
            effect_type=effect_type,
            business_key=business_key,
            params_hash=params_hash,
            idempotency_key_hash=idem_hash,
            attempt=attempt,
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
        store._append(record)
        return record

    return _add
