"""邮件模拟服务：内存账本 + 幂等键语义。"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import IdempotencyConflict, _Ledger

__all__ = ["Email", "IdempotencyConflict", "SimulatedEmailService"]


@dataclass(frozen=True)
class Email:
    notification_id: str
    subject: str
    body: str
    idempotency_key: str | None
    committed_tick: int
    ledger_sequence: int


class SimulatedEmailService:
    """参考实现：内存邮件账本，支持可开关的幂等键。"""

    def __init__(self) -> None:
        self._ledger: _Ledger[Email] = _Ledger()
        self._by_id: dict[str, Email] = {}

    def send(
        self,
        notification_id: str,
        subject: str,
        body: str,
        idempotency_key: str | None = None,
    ) -> Email:
        tick = self._ledger.next_tick()
        if idempotency_key is not None:
            existing = self._ledger.lookup(idempotency_key)
            if existing is not None:
                if (
                    existing.notification_id == notification_id
                    and existing.subject == subject
                    and existing.body == body
                ):
                    return existing
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} reused with different params"
                )

        email = Email(
            notification_id=notification_id,
            subject=subject,
            body=body,
            idempotency_key=idempotency_key,
            committed_tick=tick,
            ledger_sequence=self._ledger.size + 1,
        )
        self._ledger.register(idempotency_key, email)
        self._by_id[notification_id] = email
        return email

    def by_notification_id(self, notification_id: str) -> Email | None:
        return self._by_id.get(notification_id)

    def by_idempotency_key(self, idempotency_key: str) -> Email | None:
        return self._ledger.lookup(idempotency_key)

    def count(self) -> int:
        return self._ledger.size
