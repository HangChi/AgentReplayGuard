"""模拟服务的共享异常。"""

from __future__ import annotations


class IdempotencyConflict(Exception):
    """同一幂等键对应不同参数。"""
