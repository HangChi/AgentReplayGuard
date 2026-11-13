"""模拟服务模板（订单/邮件/库存）的幂等与重复检测语义测试。"""

from __future__ import annotations

import pytest

from agentreplayguard.services.email import Email, SimulatedEmailService
from agentreplayguard.services.inventory import InventoryOp, SimulatedInventoryService
from agentreplayguard.services.order import Order, SimulatedOrderService
from agentreplayguard.services.refund import IdempotencyConflict

# --- 订单服务 ---


def test_order_idempotent_dedup():
    service = SimulatedOrderService()
    first = service.create_order("ORD-1", 1000, idempotency_key="ik-1")
    second = service.create_order("ORD-1", 1000, idempotency_key="ik-1")

    assert first is second
    assert service.count() == 1
    assert service.by_order_id("ORD-1") is first


def test_order_duplicate_detected():
    service = SimulatedOrderService()
    service.create_order("ORD-1", 1000)
    service.create_order("ORD-1", 1000)

    assert service.count() == 2


def test_order_idempotency_conflict():
    service = SimulatedOrderService()
    service.create_order("ORD-1", 1000, idempotency_key="ik-1")

    with pytest.raises(IdempotencyConflict):
        service.create_order("ORD-1", 2000, idempotency_key="ik-1")


# --- 邮件服务 ---


def test_email_idempotent_dedup():
    service = SimulatedEmailService()
    first = service.send("N-1", "subject", "body", idempotency_key="ik-1")
    second = service.send("N-1", "subject", "body", idempotency_key="ik-1")

    assert first is second
    assert service.count() == 1
    assert service.by_notification_id("N-1") is first


def test_email_duplicate_detected():
    service = SimulatedEmailService()
    service.send("N-1", "subject", "body")
    service.send("N-1", "subject", "body")

    assert service.count() == 2


def test_email_idempotency_conflict():
    service = SimulatedEmailService()
    service.send("N-1", "subject", "body", idempotency_key="ik-1")

    with pytest.raises(IdempotencyConflict):
        service.send("N-1", "other subject", "body", idempotency_key="ik-1")


# --- 库存服务 ---


def test_inventory_idempotent_dedup():
    service = SimulatedInventoryService()
    first = service.apply("SKU-1", "deduct", 5, idempotency_key="ik-1")
    second = service.apply("SKU-1", "deduct", 5, idempotency_key="ik-1")

    assert first is second
    assert service.count() == 1


def test_inventory_duplicate_detected():
    service = SimulatedInventoryService()
    service.apply("SKU-1", "deduct", 5)
    service.apply("SKU-1", "deduct", 5)

    assert service.count() == 2


def test_inventory_idempotency_conflict():
    service = SimulatedInventoryService()
    service.apply("SKU-1", "deduct", 5, idempotency_key="ik-1")

    with pytest.raises(IdempotencyConflict):
        service.apply("SKU-1", "deduct", 10, idempotency_key="ik-1")


# --- 类型与查询 ---


def test_records_are_dataclasses():
    order = SimulatedOrderService().create_order("ORD-1", 1000)
    email = SimulatedEmailService().send("N-1", "s", "b")
    op = SimulatedInventoryService().apply("SKU-1", "deduct", 5)

    assert isinstance(order, Order)
    assert isinstance(email, Email)
    assert isinstance(op, InventoryOp)
