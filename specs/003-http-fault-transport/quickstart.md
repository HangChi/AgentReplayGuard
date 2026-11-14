# Quickstart Validation: HTTP 故障注入传输层

**Date**: 2026-11-13 | **Spec**: [spec.md](./spec.md) | **Contracts**: [http-transport-api.md](./contracts/http-transport-api.md)

本指南用于验收 003 HTTP 传输层能力，不替代 001/002 的快速开始。

## 前置条件

```bash
uv sync --extra dev --extra httpx --extra langgraph
```

如果只需验证 HTTP 能力：

```bash
uv sync --extra dev --extra httpx
```

## 1. 回归既有能力（必须不退化）

```bash
uv run pytest tests examples/refund -q
uv run ruff check .
uv run mypy src/agentreplayguard
```

预期：全部通过；未安装 httpx 的路径不受影响。

## 2. 验收同步传输层

```bash
uv run pytest tests/unit/test_http_transport.py -q
```

预期覆盖：

- 未匹配请求透传 → 账本零新增，故障计划不消耗
- 正常已分类请求 → 1 条 `committed`，返回真实响应
- 提交前故障 → `httpx.ConnectTimeout`，底层未被调用，记录 `not_committed`
- 提交后 lost-ack 重试 → 2 条 `committed`，首次抛 `httpx.ReadTimeout`
- 连接重置 / 服务端错误 / 部分成功 → `ConnectError` / `HTTPStatusError` / `ReadError`
- 底层业务异常原样传播，记录 `not_committed`
- 分类函数异常、非法业务键、不可序列化参数 → `ScenarioConfigError`，底层未被调用
- `close()` 委托底层 transport

## 3. 验收异步传输层

```bash
uv run pytest tests/unit/test_http_transport_async.py -q
```

预期覆盖：

- 异步正常请求与 lost-ack 语义与同步一致
- 异步取消 → 记录 `unknown`，`CancelledError` 传播
- 同步/异步等价场景的记录数量、状态序列与 attempt 序号一致
- `aclose()` 委托底层 transport

## 4. 验收可选依赖隔离

```bash
uv run pytest tests/contract/test_http_public_api.py -q
```

预期：

- 公开签名与契约一致
- `import agentreplayguard` 不导入 httpx 适配器
- 在模拟缺少 httpx 的环境下，导入适配器抛出含安装提示的 `ImportError`

## 5. 运行 HTTP 示例

```bash
uv run pytest examples/refund/test_refund_http.py -q
```

预期：同步与异步 lost-ack 场景均检测到同一业务键 2 条已提交退款并使不变量失败；幂等键
场景通过；全程无真实网络。

## 6. 手工最小验证

```python
import json

import httpx

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario
from agentreplayguard.adapters.httpx import FaultyTransport, HttpEffect

scenario = Scenario(
    "http-refund-lost-ack",
    seed=7,
    faults=FaultPlan(
        [
            FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
        ]
    ),
    invariants=[NoDuplicateEffects("refund")],
)


def serve(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, request=request)


def classify(request: httpx.Request) -> HttpEffect | None:
    if request.method != "POST" or not request.url.path.endswith("/refunds"):
        return None
    body = json.loads(request.content)
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


transport = FaultyTransport(httpx.MockTransport(serve), scenario, classify)
with httpx.Client(transport=transport) as client:
    for _ in range(2):
        try:
            client.post(
                "https://sim.test/refunds",
                json={"refund_id": "order-42", "amount_cents": 1000},
            )
        except httpx.ReadTimeout:
            pass

report = scenario.finish()
assert not report.ok
print(report.format())
```

预期：报告显示同一业务键 2 条 `committed`，不变量失败；无真实网络调用。

## 7. 常见错误

- 在未安装 httpx 的环境中 `from agentreplayguard.adapters.httpx import ...`：会得到带
  `pip install agentreplayguard[httpx]` 提示的 `ImportError`；核心包不受影响。
- 分类函数返回空业务键：立即抛 `ScenarioConfigError`，不会发起请求；请检查提取逻辑。
- 把只读请求也分类为写副作用：会被记账并可能触发不变量误报；只读请求应返回 `None`。
- 用 `client.stream(...)` 读取响应体：提交边界是响应头到达，响应体读取失败不在本特性
  的 lost-ack 语义内。

## 8. 覆盖率

```bash
uv run coverage run -m pytest tests examples/refund
uv run coverage report --fail-under=90
```

预期：总覆盖率 ≥90%，HTTP 适配模块纳入统计。
