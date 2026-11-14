# Quickstart: requests 适配器

**Feature**: 006-requests-adapter

```python
import json
import requests

from agentreplayguard import FaultKind, FaultPlan, FaultRule, NoDuplicateEffects, Scenario
from agentreplayguard.adapters.requests import RequestsAdapter, HttpEffect

scenario = Scenario(
    "requests-refund-lost-ack",
    seed=7,
    faults=FaultPlan(
        [
            FaultRule(FaultKind.TIMEOUT_AFTER_COMMIT, effect_type="refund", attempt=1),
        ]
    ),
    invariants=[NoDuplicateEffects("refund")],
)


def classify(request: requests.PreparedRequest) -> HttpEffect | None:
    if request.method != "POST" or "refunds" not in (request.url or ""):
        return None
    body = json.loads(request.body or b"{}")
    return HttpEffect(
        effect_type="refund",
        business_key=body["refund_id"],
        params={"amount_cents": body["amount_cents"]},
        idempotency_key=request.headers.get("Idempotency-Key"),
    )


# 用内存 mock adapter 作为底层（示例）；真实场景挂载到真实 HTTPAdapter
session = requests.Session()
adapter = RequestsAdapter(mock_base_adapter, scenario, classify)
session.mount("https://", adapter)

try:
    session.post("https://sim.test/refunds", json={"refund_id": "R-1", "amount_cents": 1000})
except requests.exceptions.ReadTimeout:
    pass  # 注入的 lost-ack 故障

report = scenario.finish()
assert not report.ok
```

## 验证

```bash
uv run pytest tests/unit/test_requests_adapter.py -q
uv run pytest -q
uv run ruff check .
uv run mypy src/agentreplayguard
uv run coverage run -m pytest -q && uv run coverage report --fail-under=90
```

## 注意

- requests 是可选依赖：`pip install agentreplayguard[requests]`。
- 注入故障映射为 requests 标准异常：`ConnectTimeout`/`ReadTimeout`/`ConnectionError`/
  `HTTPError`/`ChunkedEncodingError`。
- 分类函数返回 None 的请求（如 GET）透传，不记账、不消耗故障计划。
