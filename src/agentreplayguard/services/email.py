"""邮件模拟服务：内存账本 + 幂等键语义。"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import IdempotencyConflict

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
        self._ledger: list[Email] = []
        self._by_id: dict[str, Email] = {}
        self._by_key: dict[str, Email] = {}
        self._counter = 0

    def send(
        self,
        notification_id: str,
        subject: str,
        body: str,
        idempotency_key: str | None = None,
    ) -> Email:
        self._counter += 1
        if idempotency_key is not None and idempotency_key in self._by_key:
            existing = self._by_key[idempotency_key]
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
            committed_tick=self._counter,
            ledger_sequence=len(self._ledger) + 1,
        )
        self._ledger.append(email)
        self._by_id[notification_id] = email
        if idempotency_key is not None:
            self._by_key[idempotency_key] = email
        return email

    def by_notification_id(self, notification_id: str) -> Email | None:
        return self._by_id.get(notification_id)

    def by_idempotency_key(self, idempotency_key: str) -> Email | None:
        return self._by_key.get(idempotency_key)

    def count(self) -> int:
        return len(self._ledger)
